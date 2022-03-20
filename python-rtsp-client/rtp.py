'''
Inspired by post by Sampsa Riikonen here: 
https://stackoverflow.com/questions/28022432/receiving-rtp-packets-after-rtsp-setup

Written 2017 Mike Killian
'''

import re, socket, threading
import bitstring # if you don't have this from your linux distro, install with "pip install bitstring"

class RTPReceive(threading.Thread):
    '''
    This will open a socket on the client ports sent in RTSP setup request and
    return data as its received to the callback function. 
    '''
    def __init__(self, client_ports, callback=None):
        threading.Thread.__init__(self)
        self._callback = callback or (lambda x: None)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("", client_ports[0])) # we open a port that is visible to the whole internet (the empty string "" takes care of that)
        self._sock.settimeout(5) # if the socket is dead for 5 s., its thrown into trash
        self.closed     = False
        self.frame      = b''
        self.frame_done = True #Did we get the last packet to fill a whole frame?
        self.running    = False
        self.sprop-parameter-sets = 'Z0IAIJWoFAHmQA==,aM48gA=='
        self.start()

    def run(self):
        self.running = True
        try:
            while self.running:
                #self.frame = msg = self.recv_msg()
                msg = self._sock.recv(2048)
                framelet = self.digestpacket(msg)
                if framelet:
                    self.frame += framelet
                if self.frame and self.frame_done:
                    self._callback(self.frame)
                    self.frame = b''
        except Exception as e:
            raise Exception('Run time error: %s' % e)
        self.running = False
        self.close()

    def close(self):
        self.closed  = True
        self.running = False
        self._sock.close()

    def insert_config_info(self, parameters):
        pass
        
    # ********* (2) The routine for handling the RTP stream ***********

    def digestpacket(self, st):
        """ This routine takes a UDP packet, i.e. a string of bytes and ..
        (a) strips off the RTP header
        (b) adds NAL "stamps" to the packets, so that they are recognized as NAL's
        (c) Concantenates frames
        (d) Returns a packet that can be written to disk as such and that is recognized by stock media players as h264 stream
        """
        startbytes = b"\x00\x00\x00\x01" # this is the sequence of four bytes that identifies a NAL packet.. must be in front of every NAL packet.

        bt = bitstring.BitArray(bytes=st) # turn the whole string-of-bytes packet into a string of bits.  Very unefficient, but hey, this is only for demoing.
        lc = 12     # bytecounter
        bc = 12*8   # bitcounter

        version   = bt[0:2].uint    # Version
        p         = bt[3]           # Padding
        x         = bt[4]           # Extension
        cc        = bt[4:8].uint    # CSRC Count
        m         = bt[9]           # Marker
        pt        = bt[9:16].uint   # Payload Type
        sn        = bt[16:32].uint  # Sequence number
        timestamp = bt[32:64].uint  # Timestamp
        ssrc      = bt[64:96].uint  # ssrc identifier
        # The header format can be found from:
        # https://en.wikipedia.org/wiki/Real-time_Transport_Protocol

        lc = 12     # so, we have red twelve bytes
        bc = 12*8   # .. and that many bits

        if p:
            #TODO: Deal with padding here
            print("\n****\nPadding alert!!\n****\n")

        print("*----* Packet Begin *----* (Len: {})".format(len(st)))
        print("Ver: {}, P: {}, X: {}, CC: {}, M: {}, PT: {}".format(version,p,x,cc,m,pt))
        print("Sequence number: {}, Timestamp: {}".format(sn,timestamp))
        print("Sync. Source Identifier: {}".format(ssrc))

        # st=f.read(4*cc) # csrc identifiers, 32 bits (4 bytes) each
        cids = []
        for i in range(cc):
            cids.append(bt[bc:bc+32].uint)
            bc += 32
            lc += 4
        if cids: print("CSRC Identifiers: {}".format(cids))

        if (x):
            # this section haven't been tested.. might fail
            hid  = bt[bc:bc+16].uint
            bc  += 16
            lc  += 2

            hlen = bt[bc:bc+16].uint
            bc  += 16
            lc  += 2

            hst  = bt[bc:bc+32*hlen]
            bc  += 32*hlen
            lc  += 4*hlen

            print("*----* Extension Header *----*")
            print("Ext. Header id: {}, Header len: {}".format(hid,hlen))

        # OK, now we enter the NAL packet, as described here:
        # 
        # https://tools.ietf.org/html/rfc6184#section-1.3
        #
        # Some quotes from that document:
        #
        """
        5.3. NAL Unit Header Usage


        The structure and semantics of the NAL unit header were introduced in
        Section 1.3.  For convenience, the format of the NAL unit header is
        reprinted below:

            +---------------+
            |0|1|2|3|4|5|6|7|
            +-+-+-+-+-+-+-+-+
            |F|NRI|  Type   |
            +---------------+

        This section specifies the semantics of F and NRI according to this
        specification.

        """
        """
        Table 3.  Summary of allowed NAL unit types for each packetization
                    mode (yes = allowed, no = disallowed, ig = ignore)

            Payload Packet    Single NAL    Non-Interleaved    Interleaved
            Type    Type      Unit Mode           Mode             Mode
            -------------------------------------------------------------
            0      reserved      ig               ig               ig
            1-23   NAL unit     yes              yes               no
            24     STAP-A        no              yes               no
            25     STAP-B        no               no              yes
            26     MTAP16        no               no              yes
            27     MTAP24        no               no              yes
            28     FU-A          no              yes              yes
            29     FU-B          no               no              yes
            30-31  reserved      ig               ig               ig
        """
        # This was also very usefull:
        # http://stackoverflow.com/questions/7665217/how-to-process-raw-udp-packets-so-that-they-can-be-decoded-by-a-decoder-filter-i
        # A quote from that:
        """
        First byte:  [ 3 NAL UNIT BITS | 5 FRAGMENT TYPE BITS] 
        Second byte: [ START BIT | RESERVED BIT | END BIT | 5 NAL UNIT BITS] 
        Other bytes: [... VIDEO FRAGMENT DATA...]
        """

        fb   = bt[bc] # i.e. "F"
        nri  = bt[bc+1:bc+3].uint # "NRI"
        nlu0 = bt[bc:bc+3] # "3 NAL UNIT BITS" (i.e. [F | NRI])
        typ  = bt[bc+3:bc+8].uint # "Type"
        print("   *-* NAL Header *-*")
        print("F: {}, NRI: {}, Type: {}".format(fb, nri, typ))
        print("First three bits together : {}".format(bt[bc:bc+3]))

        if (typ==7 or typ==8):
            # this means we have either an SPS or a PPS packet
            # they have the meta-info about resolution, etc.
            # more reading for example here:
            # http://www.cardinalpeak.com/blog/the-h-264-sequence-parameter-set/
            if (typ==7):
                print(">>>>> SPS packet")
            else:
                print(">>>>> PPS packet")
            return startbytes+st[lc:]
            # .. notice here that we include the NAL starting sequence "startbytes" and the "First byte"

        bc += 8; 
        lc += 1; # let's go to "Second byte"
        # ********* WE ARE AT THE "Second byte" ************
        # The "Type" here is most likely 28, i.e. "FU-A"
        start = bt[bc] # start bit
        end   = bt[bc+2] # end bit
        nlu1  = bt[bc+3:bc+8] # 5 nal unit bits
        head = b""

        if (self.frame_done and start): # OK, this is a first fragment in a movie frame
            print(">>> first fragment found")
            self.frame_done = False
            nlu  = nlu0+nlu1 # Create "[3 NAL UNIT BITS | 5 NAL UNIT BITS]"
            print("  >>> NLU0: {}, NLU1: {}, NLU: {}".format(nlu0,nlu1,nlu))
            head = startbytes+nlu.bytes # .. add the NAL starting sequence
            lc  += 1 # We skip the "Second byte"
        elif (self.frame_done==False and start==False and end==False): # intermediate fragment in a sequence, just dump "VIDEO FRAGMENT DATA"
            lc  += 1 # We skip the "Second byte"
        elif (self.frame_done==False and end==True): # last fragment in a sequence, just dump "VIDEO FRAGMENT DATA"
            print("<<<< last fragment found")
            self.frame_done = True
            lc  += 1 # We skip the "Second byte"

        if (typ==28): # This code only handles "Type" = 28, i.e. "FU-A"
            return head+st[lc:]
        else:
            #raise Exception("unknown frame type for this piece of s***")
            return None
