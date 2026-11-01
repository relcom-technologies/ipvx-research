"""Durable SHA-256 worker. A delivery/worker gap stays UNKNOWN, never auto-replayed."""
import sqlite3
from bcp.wire import digest, uint, require


class Worker:
    def __init__(self, db):
        self.db = db
        db.execute('CREATE TABLE IF NOT EXISTS worker (source BLOB,message BLOB,request BLOB,state TEXT,result BLOB, PRIMARY KEY(source,message))')

    def accept(self, frame, plaintext, disposition):
        f = frame.fields; key = (uint(f['source'],32), f['message'])
        old = self.db.execute('SELECT request,state,result FROM worker WHERE source=? AND message=?', key).fetchone()
        if old:
            require(old[0] == f['request_hash'], 'MESSAGE_CONFLICT')
            return old[2] if old[1] == 'DONE' else None
        if disposition != 'NEW':
            return None
        self.db.execute('INSERT INTO worker VALUES (?,?,?,\'STARTED\',NULL)', (*key, f['request_hash']))
        result = digest(plaintext)
        self.db.execute('UPDATE worker SET state=\'DONE\', result=? WHERE source=? AND message=?', (result,*key))
        return result


class Scheduler:
    """One in-flight original; no autonomous allocation or replacement IDs."""
    def __init__(self, *, clock, attempts=3, timeout=5):
        require(type(attempts) is int and 1 <= attempts <= 3 and timeout == 5, 'POLICY_DENIED')
        self.clock, self.maximum, self.timeout = clock, attempts, timeout
        self.pending = None; self.total = 0; self.originals = set()

    def begin(self, message, frame, plaintext):
        require(self.pending is None and self.total < 120, 'POLICY_DENIED')
        self.originals.add(message)
        require(len(self.originals) <= 40, 'POLICY_DENIED')
        self.pending = dict(message=message, frame=frame, plaintext=plaintext, count=0,
                            started=self.clock(), deadline=self.clock())

    def due(self):
        p = self.pending
        if p is None or self.clock() < p['deadline']:
            return 'WAIT'
        if p['count'] >= self.maximum or self.clock()-p['started'] >= 20:
            return 'UNKNOWN'
        require(self.total < 120, 'POLICY_DENIED')
        p['count'] += 1; self.total += 1; p['deadline'] = self.clock()+self.timeout
        return 'SEND'

    def finish(self, message):
        require(self.pending is not None and message == self.pending['message'], 'UNKNOWN')
        old = self.pending; self.pending = None
        return old
