"""Bounded classic Ethernet PCAP; all EtherTypes retained and audited."""
import struct
from .common import need


class Writer:
    def __init__(self,file, *, budget=128*1024**2):
        self.file,self.budget,self.bytes=file,budget,24
        file.write(struct.pack('<IHHIIII',0xa1b2c3d4,2,4,0,0,65535,1));file.flush()

    def append(self, raw, timestamp):
        need(len(raw)<=65535 and self.bytes+16+len(raw)<=self.budget,'capture budget exhausted')
        seconds=int(timestamp);micros=int((timestamp-seconds)*1e6)
        self.file.write(struct.pack('<IIII',seconds,micros,len(raw),len(raw))+raw);self.file.flush()
        self.bytes+=16+len(raw)


def frames(file):
    head=file.read(24)
    need(len(head)==24,'missing PCAP header')
    magic,major,minor,zone,sig,snap,link=struct.unpack('<IHHIIII',head)
    need((magic,major,minor,zone,sig,snap,link)==(0xa1b2c3d4,2,4,0,0,65535,1),'unsupported PCAP header')
    while True:
        entry=file.read(16)
        if not entry:break
        need(len(entry)==16,'truncated PCAP record')
        seconds,micros,included,original=struct.unpack('<IIII',entry)
        need(0<=micros<1000000 and 14<=included==original<=65535,'truncated/invalid capture length')
        raw=file.read(included);need(len(raw)==included,'missing captured bytes')
        yield seconds+micros/1e6,raw
