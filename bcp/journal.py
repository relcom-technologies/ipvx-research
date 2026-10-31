"""Durable checkpoint and application linkage journal; never executes a task.

Rows are retained indefinitely in this minimal core (at least seven days). There
is deliberately no purge, automatic retry, new-message-ID or recovery shortcut.
The caller must use a private directory. Link sessions are not persisted.
"""
import sqlite3
from .wire import Checkpoint, Reader, Reject, digest, require, uint


class Journal:
    def __init__(self, path=':memory:'):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value BLOB NOT NULL);
          CREATE TABLE IF NOT EXISTS requests (
            source BLOB, destination BLOB, message BLOB, request BLOB, plaintext BLOB,
            PRIMARY KEY(source,message));
          CREATE TABLE IF NOT EXISTS deliveries (
            source BLOB, message BLOB, request BLOB, PRIMARY KEY(source,message));
          CREATE TABLE IF NOT EXISTS receipts (
            source BLOB, message BLOB, phase INTEGER, result BLOB, error INTEGER,
            PRIMARY KEY(source,message));
        ''')

    def close(self):
        self.db.close()

    def checkpoint(self, checkpoint, extends_saved=None):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            require(self.db.execute("SELECT 1 FROM meta WHERE key='conflict'").fetchone() is None, 'STATE_CONFLICT')
            row = self.db.execute("SELECT value FROM meta WHERE key='checkpoint'").fetchone()
            if row:
                old = Checkpoint.read(Reader(row[0]))
                if checkpoint.number < old.number:
                    raise Reject('STATE_CONFLICT')
                conflict = ((checkpoint.number == old.number and checkpoint != old)
                            or (checkpoint.number > old.number and extends_saved is False))
                if conflict:
                    self.db.execute("INSERT OR REPLACE INTO meta VALUES ('conflict', X'01')")
                    self.db.execute('COMMIT')
                    raise Reject('STATE_CONFLICT')
                if checkpoint.number > old.number:
                    require(extends_saved is True, 'STATE_UNAVAILABLE')
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('checkpoint', ?)", (checkpoint.encode(),))
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def remember_request(self, source, destination, message, request_hash, plaintext):
        require(digest(plaintext) == request_hash, 'INVALID_PAYLOAD')
        args = (uint(source,32), uint(destination,32), message, request_hash, plaintext)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT destination,request,plaintext FROM requests WHERE source=? AND message=?',
                                  (args[0], message)).fetchone()
            require(old is None or old == (args[1], request_hash, plaintext), 'MESSAGE_CONFLICT')
            self.db.execute('INSERT OR IGNORE INTO requests VALUES (?,?,?,?,?)', args)
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK'); raise

    def deliver(self, source, message, request_hash):
        key = (uint(source,32), message)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT request FROM deliveries WHERE source=? AND message=?', key).fetchone()
            require(row is None or row[0] == request_hash, 'MESSAGE_CONFLICT')
            self.db.execute('INSERT OR IGNORE INTO deliveries VALUES (?,?,?)', (*key,request_hash))
            self.db.execute('COMMIT')
            return 'NEW' if row is None else 'DUPLICATE'
        except BaseException:
            self.db.execute('ROLLBACK'); raise

    def receipt(self, requester, responder, message, request_hash, phase, result, error=None):
        """Unknown original state remains UNKNOWN; ERROR never rolls back COMPLETED."""
        require(phase in (0,1,2) and (phase != 1 or result == b'')
                and ((phase == 0 and type(error) is int and 1 <= error <= 20)
                     or (phase in (1,2) and error is None)), 'INVALID_PAYLOAD')
        key = (uint(requester,32), message)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            original = self.db.execute('SELECT destination,request FROM requests WHERE source=? AND message=?', key).fetchone()
            require(original is not None, 'UNKNOWN')
            require(original == (uint(responder,32), request_hash), 'INVALID_PAYLOAD')
            old = self.db.execute('SELECT phase,result,error FROM receipts WHERE source=? AND message=?', key).fetchone()
            if phase == 0 and old:
                self.db.execute('UPDATE receipts SET error=? WHERE source=? AND message=?',(error,*key))
            elif old and old[0] == 2:
                require(phase != 2 or old[1] == digest(result), 'MESSAGE_CONFLICT')
            elif not old or phase == 2 or (phase == 1 and old[0] == 0):
                self.db.execute('INSERT OR REPLACE INTO receipts VALUES (?,?,?,?,?)',
                                (*key,phase,digest(result),error))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK'); raise
