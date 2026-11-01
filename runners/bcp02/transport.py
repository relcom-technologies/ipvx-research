"""Linux packet sockets, bound to a single interface. Tests inject socket/ifindex APIs."""
import socket
import struct
import sys

from .common import Blocked, need

SOL_PACKET, PACKET_STATISTICS, PACKET_OUTGOING = 263, 6, 4
MAX_FRAME = 1514


class PacketPort:
    def __init__(self, name, *, capture=False, api=socket):
        need(sys.platform == 'linux' or api is not socket, 'Linux AF_PACKET required')
        self.api, self.name, self.capture = api, name, capture
        self.ifindex = api.if_nametoindex(name)
        need(self.ifindex > 0, 'interface missing')
        self.sock = api.socket(api.AF_PACKET, api.SOCK_RAW, api.htons(3 if capture else 0x88b5))
        try:
            self.sock.bind((name, 0))
            self.sock.setblocking(False)
            self.sock.setsockopt(api.SOL_SOCKET, api.SO_RCVBUF, 4 * 1024 * 1024)
        except BaseException:
            self.sock.close(); raise

    def fileno(self):
        return self.sock.fileno()

    def recv(self):
        buf = bytearray(65535 if self.capture else MAX_FRAME)
        length, anc, flags, address = self.sock.recvmsg_into([buf], 0, self.api.MSG_TRUNC)
        need(address[0] == self.name and self.api.if_nametoindex(address[0]) == self.ifindex,
             'RX interface changed')
        if not self.capture and address[2] == PACKET_OUTGOING:
            return None
        need(not flags & self.api.MSG_TRUNC and length <= len(buf), 'truncated Ethernet frame')
        raw = bytes(buf[:length])
        need(length >= 14, 'short Ethernet frame')
        if not self.capture:
            need(raw[12:14] == b'\x88\xb5' and length <= MAX_FRAME, 'invalid BCP Ethernet binding')
        return raw

    def send(self, raw):
        need(not self.capture and type(raw) is bytes and 14 <= len(raw) <= MAX_FRAME
             and raw[12:14] == b'\x88\xb5', 'invalid TX frame')
        need(self.api.if_nametoindex(self.name) == self.ifindex, 'TX interface changed')
        need(self.sock.send(raw) == len(raw), 'partial packet send')

    def statistics(self):
        packets, drops = struct.unpack('II', self.sock.getsockopt(SOL_PACKET, PACKET_STATISTICS, 8))
        return dict(packets=packets, drops=drops, ifindex=self.ifindex, unfiltered=self.capture)

    def close(self):
        self.sock.close()
