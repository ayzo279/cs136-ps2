#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers 
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer

class BarazStd(Peer):
    def post_init(self):
        print(("post_init(): %s here!" % self.id))
        self.dummy_state = dict()
        self.dummy_state["cake"] = "lie"
        self.lucky = self.id
    
    def requests(self, peers, history):
        """
        peers: available info about the peers (who has what pieces)
        history: what's happened so far as far as this peer can see

        returns: a list of Request() objects

        This will be called after update_pieces() with the most recent state.
        """
        needed = lambda i: self.pieces[i] < self.conf.blocks_per_piece
        needed_pieces = list(filter(needed, list(range(len(self.pieces)))))
        np_set = set(needed_pieces)  # sets support fast intersection ops.



        logging.debug("%s here: still need pieces %s" % (
            self.id, needed_pieces))

        logging.debug("%s still here. Here are some peers:" % self.id)
        for p in peers:
            logging.debug("id: %s, available pieces: %s" % (p.id, p.available_pieces))

        logging.debug("And look, I have my entire history available too:")
        logging.debug("look at the AgentHistory class in history.py for details")
        logging.debug(str(history))

        requests = []   # We'll put all the things we want here
        # Symmetry breaking is good...
        random.shuffle(needed_pieces)
        
        # Sort peers by id.  This is probably not a useful sort, but other 
        # sorts might be useful
        peers.sort(key=lambda p: p.id)

        # Get frequency counts of available needed pieces:
        pieces_ranking = {}
        for pc in needed_pieces:
            pieces_ranking[pc] = 0
        for peer in peers:
            for peer_pc in peer.available_pieces:
                if peer_pc in pieces_ranking.keys():
                    pieces_ranking[peer_pc] += 1
        ranked_pieces = {k: v for k, v in sorted(pieces_ranking.items(), key=lambda x: x[1])}

        # request all available pieces from all peers!
        # (up to self.max_requests from each)
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(np_set)
            n = min(self.max_requests, len(isect))
            # More symmetry breaking -- ask for random pieces.
            # This would be the place to try fancier piece-requesting strategies
            # to avoid getting the same thing from multiple peers at a time.
            isect_pieces = []
            for pc in ranked_pieces:
                if pc in isect:
                    isect_pieces.append(pc)
            for i in range(n):
                # aha! The peer has this piece! Request it.
                # which part of the piece do we need next?
                # (must get the next-needed blocks in order)
                start_block = self.pieces[isect_pieces[i]]
                r = Request(self.id, peer.id, isect_pieces[i], start_block)
                requests.append(r)

        return requests

    def uploads(self, requests, peers, history):
        """
        requests -- a list of the requests for this peer for this round
        peers -- available info about all the peers
        history -- history for all previous rounds

        returns: list of Upload objects.

        In each round, this will be called after requests().
        """

        round = history.current_round()
        prev = max(0, round - 1)
        prev_prev = max(prev, round - 2)

        logging.debug("%s again.  It's round %d." % (
            self.id, round))
        logging.debug("Printing history...%s" % history.downloads)
        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course)
        # has a list of Download objects for each Download to this peer in
        # the previous round.

        # Iterate through peers and count how much they've sent to this agent   
        random.shuffle(peers)
        peer_uploads = {}
        num_sharers = 0
        for peer in peers:
            peer_uploads[peer.id] = 0

        if round != 0:
            for download in history.downloads[prev]:
                peer_uploads[download.from_id] += download.blocks/2
            for download in history.downloads[prev_prev]:
                peer_uploads[download.from_id] += download.blocks/2

        for val in peer_uploads.values():
            if val > 0:
                num_sharers += 1
        sorted_peers = {k: v for k, v in sorted(peer_uploads.items(), key=lambda x: x[1], reverse=True)}

        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
            chosen = []
            bws = []
            uploads = []
        else:
            logging.debug("Still here: uploading to a random peer")
            # change my internal state for no reason
            self.dummy_state["cake"] = "pie"
            extra_unblock = -1
            if (round != 0 and round != 1):
                to_unblock = min(min(num_sharers + 1, 4), len(peers))
                bws = even_split(self.up_bw, to_unblock)
                extra_unblock = bws.pop()
            else:   
                to_unblock = min(min(num_sharers + 1, 3), len(peers))
                bws = even_split(self.up_bw, to_unblock)
            
            unblocked = set()
            requesting_ids = set([request.requester_id for request in requests])
            
            # request = random.choice(requests)
            # chosen = [request.requester_id]
            uploads = []
            # Evenly "split" my upload bandwidth among the one chosen requester

            for peer in sorted_peers.keys():
                if bws != []:
                    if peer in requesting_ids:
                        uploads.append(Upload(self.id, peer, bws.pop()))
                        unblocked.add(peer)
            
            # Opportunistic unblocking
            if (round % 3 == 2):
                opp_req = requesting_ids.difference(unblocked)
                if len(opp_req) != 0 :
                    self.lucky = random.sample(opp_req, 1)
            if self.lucky != self.id:
                uploads.append(Upload(self.id, self.lucky, extra_unblock))
                
            
        return uploads


        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]
            
        return uploads
