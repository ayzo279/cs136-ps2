#!/usr/bin/python

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer

class BarazTourney(Peer):
    def post_init(self):
        print(("post_init(): %s here!" % self.id))
        self.dummy_state = dict()
        self.dummy_state["cake"] = "lie"
        self.lucky = self.id
        self.spite = dict()
        self.requested = set()
        
    
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
            isect_pieces = sorted(isect, key=lambda x: pieces_count[x])

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

        # Increment "spite" count against those who did not satisfy a request from last round
        if round == 0:
            for peer in peers:
                self.spite[peer.id] = 0
        up_to_me = set()
        unrequited = set()
        if round > 2:
            for download in history.downloads[prev]:
                up_to_me.add(download.from_id)
            for uploader in up_to_me:
                # Reset spite counter if a request was satisfied
                if self.spite[uploader] > 0:
                    self.spite[uploader] = 0
            unrequited = self.requested.difference(up_to_me)
        for peer in unrequited:
            self.spite[peer] += 1

        needed = lambda i: self.pieces[i] < self.conf.blocks_per_piece
        needed_pieces = list(filter(needed, list(range(len(self.pieces)))))
        # Intialize a set of all the IDs of requesters
        requesting_ids = set()
        for request in requests:
            if self.spite[request.requester_id] < 3: 
                requesting_ids.add(request.requester_id)
        # Regular unblock of at most 3 peers
        unblocked = set()

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

            # Iterate through randomly shuffled peers and count how much they've sent to this agent   
            random.shuffle(peers)
            peer_uploads = {}
            num_sharers = 0

            # Initialize peers dictionary to keep track of received downloads
            for peer in peers:
                peer_uploads[peer.id] = 0

            # Set each peer's uploads as average from previous two rounds
            if round > 1:
                for download in history.downloads[prev]:
                    peer_uploads[download.from_id] += download.blocks/2
                for download in history.downloads[prev_prev]:
                    peer_uploads[download.from_id] += download.blocks/2
            elif round == 1:
                for download in history.downloads[prev]:
                    peer_uploads[download.from_id] += download.blocks

            # Count how many peers uploaded anything at all to me
            for val in peer_uploads.values():
                if val > 0:
                    num_sharers += 1

            # Sort received downloads in descending order
            sorted_peers = {k: v for k, v in sorted(peer_uploads.items(), key=lambda x: x[1], reverse=True)}

            for peer in sorted_peers.keys():
                if len(unblocked) < 3:
                    if peer in requesting_ids and peer != self.lucky:
                        # uploads.append(Upload(self.id, peer, bws.pop()))
                        unblocked.add(peer)
                else:
                    break
            # Optimistic unblocking every 3 rounds
            if round % 3 == 0:
                # Take difference of requesters and regularly unblocked peers
                opt_req = requesting_ids.difference(unblocked)
                if len(opt_req) != 0:
                    self.lucky = random.sample(opt_req, 1)[0]
            if self.id != self.lucky:
                unblocked.add(self.lucky)
            
            
            # Evenly "split" my upload bandwidth among unblocked peers
            to_unblock = len(unblocked)
            bws = even_split(self.up_bw, to_unblock)
            for peer in unblocked:
                uploads.append(Upload(self.id, peer, bws.pop()))

        return uploads
