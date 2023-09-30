#!/usr/bin/python

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer

class BarazTyrant(Peer):
    def post_init(self):
        print(("post_init(): %s here!" % self.id))
        self.dummy_state = dict()
        self.dummy_state["cake"] = "lie"
        
        self.d_i = {} # tracks d_i
        self.u_i = {} # tracks u_i
        self.prev_unblocks = {} # tracks how many blocks peers gave to us the last time they unblocked us
        self.unblockers = [] # list of sets of peers who unblocked us (appended to each round)
    
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
        # peers.sort(key=lambda p: p.id)

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

        # Initizalize empty list of uploads
        uploads = []

        # In round 0, initialize dictionaries to keep track of d_i, u_i, and 
        # how many blocks were given to us the last time a peer unblocked us
        if round == 0:
            random.shuffle(peers)
            for peer in peers:
                self.d_i[peer.id] = 0
                self.u_i[peer.id] = 14 # min-bw
                self.prev_unblocks[peer.id] = 0 # number of blocks we were given by this peer
            
            return uploads

        logging.debug("%s again.  It's round %d." % (
            self.id, round))

        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course)
        # has a list of Download objects for each Download to this peer in
        # the previous round.
        logging.debug("Printing history...%s" % history.downloads)

        # Track who unblocked us in last round
        set_prev_unblockers = set()
        for download in history.downloads[prev]:
            self.prev_unblocks[download.from_id] = download.blocks
            set_prev_unblockers.add(download.from_id)
        self.unblockers.append(set_prev_unblockers)

        # Estimate d_i
        requesting_ids = [request.requester_id for request in requests]
        for requester in requesting_ids:
            for peer in peers:
                if peer.id == requester:
                    if self.prev_unblocks[requester] != 0: # they did unblock us in a previous round
                        self.d_i[requester] = self.prev_unblocks[requester]
                    else: # they have not unblocked us in a previous round
                        self.d_i[requester] = len(peer.available_pieces) / (prev * 4)

        # Track who we unblocked in last round
        set_prev_receivers = set()
        for upload in history.uploads[prev]:
            set_prev_receivers.add(upload.to_id)

        # Estimate u_i
        alpha = 0.2
        gamma = 0.1
        
        for requester in requesting_ids:
            for peer in peers:
                if peer.id == requester:
                    # If we unblocked them, but they did not unblock us
                    if requester in set_prev_receivers and requester not in set_prev_unblockers:
                        self.u_i[requester] *= (1 + alpha)
                    # If they unblock us for the last 3 rounds in a row
                    elif requester in self.unblockers[-1] and requester in self.unblockers[-2] and requester in self.unblockers[-3]:
                        self.u_i[requester] *= (1 - gamma)
        
        # Calculate ROI = d_i / u_i
        di_ui = {}
        for requester in requesting_ids:
            di_ui[requester] = self.d_i[requester] / self.u_i[requester]

        # Sort requesters by ROI in descending order
        sorted_requesters = {k: v for k, v in sorted(di_ui.items(), key=lambda x: x[1], reverse=True)}
        
        bw_remaining = self.up_bw
        for peer in sorted_requesters:
            bw_required = self.u_i[peer]
            if bw_remaining - bw_required > 0:
                uploads.append(Upload(self.id, peer, bw_required))
                bw_remaining -= bw_required
            else:
                uploads.append(Upload(self.id, peer, int(bw_remaining)))
                break

        return uploads
