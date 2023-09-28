#!/usr/bin/python

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer

class BarazPropShare(Peer):
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

        # Get frequency counts of available needed pieces:
        pieces_count = {}
        for pc in needed_pieces:
            pieces_count[pc] = 0
        for peer in peers:
            for peer_pc in peer.available_pieces:
                if peer_pc in pieces_count.keys():
                    pieces_count[peer_pc] += 1

        # Sorts pieces based on ascending count for rarity
        ranked_pieces = {k: v for k, v in sorted(pieces_count.items(), key=lambda x: x[1])}

        # request all available pieces from all peers!
        # (up to self.max_requests from each)
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = list(av_set.intersection(np_set))
            n = min(self.max_requests, len(isect))
            # More symmetry breaking -- ask for random pieces.
            # This would be the place to try fancier piece-requesting strategies
            # to avoid getting the same thing from multiple peers at a time.
            random.shuffle(isect)
            isect_pieces = sorted(isect, key=lambda x: ranked_pieces[x])

            for i in range(n):
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
        prev_prev = max(0, round - 2)

        logging.debug("%s again.  It's round %d." % (
            self.id, round))

        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course)
        # has a list of Download objects for each Download to this peer in
        # the previous round.
        logging.debug("Printing history...%s" % history.downloads)

        # Initizalize empty list of uploads
        uploads = []

        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
            
        else:
            logging.debug("Still here: uploading my pieces!")

            # Randomly shuffle to break symmetry  
            random.shuffle(peers)
            
            # Get intersection of received downloads from previous round and requesters
            requesting_ids = set([request.requester_id for request in requests])
            unblocked = set()
            last_received = {}
            to_assign = {}
            total_received = 0

            for download in history.downloads[prev]:
                if download.from_id in requesting_ids:
                    # Increment total received
                    total_received += download.blocks
                    # Store how much was received from each agent
                    last_received[download.from_id] = download.blocks
                    # Add to set of agent to unblock
                    unblocked.add(download.from_id)
            # Add padding for optimistic unblocking        
            total_received += total_received/9

            # Assign proportion of bandwidth based on how much was received 
            for requester in last_received.keys():
                to_assign[requester] = last_received[requester]/total_received

            # Get set of agents who didn't upload to me
            opt_req = requesting_ids.difference(unblocked)
            if len(opt_req) != 0:
                # Pick someone to optimistically unblock and give 10% of bandwidth
                lucky = random.sample(opt_req, 1)[0]
                if unblocked == set():
                    to_assign[lucky] = 1
                else:
                    to_assign[lucky] = 0.1
            else:
                # Redistribute remaining 10 percent if optimistic unblocking not possible
                for req in to_assign.keys():
                    to_assign[req] += (to_assign[req]/0.9)*0.1
                
            # Assign bandwidths as proportion of received downloads
            for peer in to_assign.keys():
                uploads.append(Upload(self.id, peer, int(to_assign[peer] * self.up_bw)))

        return uploads
