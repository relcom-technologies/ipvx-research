"""Durable adapter checkpoint, binding and conflict latch; no automatic reset."""
from dataclasses import dataclass
import sqlite3
from bcp.wire import Checkpoint, Reader, require, uint


@dataclass(frozen=True)
class SavedPoint:
    execution: Checkpoint
    cl_root: bytes
    cl_slot: int


class Store:
    def __init__(self, path, fingerprint):
        self.fingerprint=fingerprint
        self.db=sqlite3.connect(path,isolation_level=None)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS adapter_state (
            id INTEGER PRIMARY KEY CHECK(id=1), binding BLOB NOT NULL,
            checkpoint BLOB, cl_root BLOB, cl_slot BLOB, conflict INTEGER NOT NULL)''')
        self.db.execute('INSERT OR IGNORE INTO adapter_state VALUES (1,?,NULL,NULL,NULL,0)',(fingerprint,))
        if self.db.execute('SELECT binding FROM adapter_state WHERE id=1').fetchone()[0]!=fingerprint:
            self.db.close()
            raise ValueError('adapter store belongs to another explicit binding')

    def close(self):
        self.db.close()

    def get(self):
        cp,root,slot,conflict=self.db.execute('SELECT checkpoint,cl_root,cl_slot,conflict FROM adapter_state WHERE id=1').fetchone()
        require(conflict==0,'STATE_CONFLICT')
        return None if cp is None else SavedPoint(Checkpoint.read(Reader(cp)),root,int.from_bytes(slot,'big'))

    def latch(self):
        self.db.execute('UPDATE adapter_state SET conflict=1 WHERE id=1')

    def save(self, expected, point):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            require(self.get()==expected,'STATE_UNAVAILABLE')
            self.db.execute('UPDATE adapter_state SET checkpoint=?,cl_root=?,cl_slot=? WHERE id=1',
                            (point.execution.encode(),point.cl_root,uint(point.cl_slot,8)))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise
