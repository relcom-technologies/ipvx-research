"""Linux packet sockets, bound to a single interface. Tests inject socket/ifindex APIs."""
import errno
import fcntl
import socket
import struct
import sys

from .common import Blocked, need

SOL_PACKET, PACKET_STATISTICS, PACKET_OUTGOING = 263, 6, 4
SIOCGIFINDEX = 0x8933
MAX_FRAME = 1514


class PacketPort:
    def __init__(self, name, *, capture=False, api=socket, ioctl=fcntl.ioctl):
        need(sys.platform == 'linux' or api is not socket, 'Linux AF_PACKET required')
        self.api, self.name, self.capture, self.ioctl = api, name, capture, ioctl
        self.ifindex = api.if_nametoindex(name)
        need(self.ifindex > 0, 'interface missing')
        self.sock = api.socket(api.AF_PACKET, api.SOCK_RAW, api.htons(3 if capture else 0x88b5))
        try:
            self.sock.bind((name, 0))
            # Binding to a link that is still down leaves ENETDOWN pending; the kernel
            # hooks the socket at link-up. Only captures start before link-up.
            error = self.sock.getsockopt(api.SOL_SOCKET, api.SO_ERROR)
            need(error == 0 or (capture and error == errno.ENETDOWN), 'packet socket bind error')
            self.sock.setblocking(False)
            self.sock.setsockopt(api.SOL_SOCKET, api.SO_RCVBUF, 4 * 1024 * 1024)
        except BaseException:
            self.sock.close(); raise

    def fileno(self):
        return self.sock.fileno()

    def current_ifindex(self):
        # Not if_nametoindex(): glibc opens a socket for it, which isolated children may not do.
        request = struct.pack('40s', self.name.encode())
        return struct.unpack_from('i', self.ioctl(self.sock.fileno(), SIOCGIFINDEX, request), 16)[0]

    def recv(self):
        buf = bytearray(65535 if self.capture else MAX_FRAME)
        length, anc, flags, address = self.sock.recvmsg_into([buf], 0, self.api.MSG_TRUNC)
        need(address[0] == self.name and self.current_ifindex() == self.ifindex,
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
        need(self.current_ifindex() == self.ifindex, 'TX interface changed')
        need(self.sock.send(raw) == len(raw), 'partial packet send')

    def statistics(self):
        packets, drops = struct.unpack('II', self.sock.getsockopt(SOL_PACKET, PACKET_STATISTICS, 8))
        return dict(packets=packets, drops=drops, ifindex=self.ifindex, unfiltered=self.capture)

    def close(self):
        self.sock.close()
