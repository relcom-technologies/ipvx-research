"""Strict RPC/ABI decoding; Ethereum Keccak is deliberately not SHA3-256."""
import re
from Crypto.Hash import keccak
from bcp.wire import Checkpoint, digest, require, uint

CHAIN_ID = 11155111
GENESIS = bytes.fromhex('25a5cc106eea7138acab33231d7160d69cb777ee0c2c553fcddf5138993e6dd9')


def keccak256(data):
    return keccak.new(digest_bits=256, data=data).digest()


def hexdata(value, size=None):
    require(type(value) is str and re.fullmatch(r'0x(?:[0-9a-fA-F]{2})*', value) is not None, 'STATE_UNAVAILABLE')
    raw = bytes.fromhex(value[2:])
    require(size is None or len(raw) == size, 'STATE_UNAVAILABLE')
    return raw


def hx(value):
    return '0x'+value.hex()


def quantity(value):
    require(type(value) is str and re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)', value) is not None, 'STATE_UNAVAILABLE')
    number = int(value,16)
    require(number < 2**64, 'STATE_UNAVAILABLE')
    return number


def decimal(value):
    require(type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]*)', value) is not None, 'STATE_UNAVAILABLE')
    number = int(value)
    require(number < 2**64, 'STATE_UNAVAILABLE')
    return number


def execution_header(value):
    require(type(value) is dict, 'STATE_UNAVAILABLE')
    cp = Checkpoint(quantity(value['number']),hexdata(value['hash'],32),hexdata(value['stateRoot'],32),quantity(value['timestamp']))
    require(any(cp.block_hash) and any(cp.state_root), 'STATE_UNAVAILABLE')
    return cp,hexdata(value['parentHash'],32)


def beacon_header(value):
    require(type(value) is dict and value['execution_optimistic'] is False, 'FINALITY_REQUIRED')
    require(value['finalized'] is True and value['data']['canonical'] is True, 'FINALITY_REQUIRED')
    data = value['data']; m = data['header']['message']; root = hexdata(data['root'],32)
    slot,proposer = decimal(m['slot']),decimal(m['proposer_index'])
    parent = hexdata(m['parent_root'],32)
    chunks = [slot.to_bytes(8,'little')+b'\0'*24,proposer.to_bytes(8,'little')+b'\0'*24,
              parent,hexdata(m['state_root'],32),hexdata(m['body_root'],32),b'\0'*32,b'\0'*32,b'\0'*32]
    while len(chunks)>1:
        chunks=[digest(chunks[i]+chunks[i+1]) for i in range(0,len(chunks),2)]
    require(chunks[0] == root, 'STATE_UNAVAILABLE')
    hexdata(data['header']['signature'],96)  # BLS verification belongs to the trusted CL.
    return root,slot,parent,m,data['header']['signature']


SIGNATURES = {
    'node':'node(uint256)', 'ownerOf':'ownerOf(uint256)', 'edge':'edge(bytes32)',
    'connection':'connection(bytes32)', 'allowsEdge':'allowsEdge(bytes32,bytes32)',
    'registry':'registry()', 'transit':'transit()',
}


def calldata(name, *args):
    return hx(keccak256(SIGNATURES[name].encode())[:4]+b''.join(uint(a,32) if type(a) is int else a for a in args))


def abi_words(value, widths):
    raw=hexdata(value)
    require(len(raw)==32*len(widths), 'STATE_UNAVAILABLE')
    values=[]
    for i,width in enumerate(widths):
        word=raw[i*32:(i+1)*32]
        if width=='bytes32':values.append(word)
        else:
            number=int.from_bytes(word,'big')
            require(number < 2**width, 'STATE_UNAVAILABLE')
            values.append(word[12:] if width==160 else number)
    return tuple(values)


def no_proxy_opcodes(code):
    require(0 < len(code) <= 24576, 'STATE_UNAVAILABLE')
    i=0
    while i<len(code):
        op=code[i]
        require(op not in (0xf2,0xf4,0xff), 'STATE_UNAVAILABLE')
        i+=1+(op-0x5f if 0x60<=op<=0x7f else 0)
    # This complements approved runtime hash pins; it is not a generic proxy audit.
