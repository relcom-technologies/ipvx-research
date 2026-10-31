"""Scoped core journal with a trusted checkpoint getter and ancestry CAS.

Existing request/delivery/receipt storage semantics and schema are inherited.
One integration instance operates a journal at a time. Separate adapter/core
databases do not form an atomic transaction or an application execution ledger.
"""
from contextlib import contextmanager
import threading

from bcp.journal import Journal
from bcp.wire import Checkpoint,Reader,Reject,digest,domain,fixed,require,uint

_UNSET=object()


class BoundJournal(Journal):
    def __init__(self,path,profile,local_nft):
        self.binding=domain('integrated-journal')+fixed(profile,32)+uint(local_nft,32)
        self.profile,self.local_nft=profile,local_nft
        self._lock=threading.Lock();self._expected=_UNSET
        super().__init__(path)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            row=self.db.execute("SELECT value FROM meta WHERE key='integration_binding'").fetchone()
            if row is None:
                # A populated legacy journal has no established chain/node scope.
                empty=all(self.db.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchone() is None
                          for table in ('meta','requests','deliveries','receipts'))
                require(empty,'STATE_CONFLICT')
                self.db.execute("INSERT INTO meta VALUES ('integration_binding',?)",(self.binding,))
            else:require(row[0]==self.binding,'STATE_CONFLICT')
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            self.close();raise

    def saved_checkpoint(self):
        values=dict(self.db.execute("SELECT key,value FROM meta WHERE key IN ('checkpoint','conflict','integration_binding')"))
        require(values.get('integration_binding')==self.binding and 'conflict' not in values,'STATE_CONFLICT')
        if 'checkpoint' not in values:return None
        reader=Reader(values['checkpoint']);point=Checkpoint.read(reader);reader.done()
        return point

    @contextmanager
    def guard(self):
        require(self._lock.acquire(blocking=False),'STATE_UNAVAILABLE')
        try:
            self._expected=self.saved_checkpoint()
            yield self._expected
        finally:
            self._expected=_UNSET;self._lock.release()

    def checkpoint(self,point,extends_saved=None):
        # Same gates as the frozen core Journal, plus an atomic comparison with
        # the exact journal point whose ancestry the adapter actually checked.
        require(self._expected is not _UNSET,'STATE_UNAVAILABLE')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old=self.saved_checkpoint()
            require(old==self._expected,'STATE_UNAVAILABLE')
            if old is not None:
                require(point.number>=old.number,'STATE_CONFLICT')
                conflict=((point.number==old.number and point!=old)
                          or (point.number>old.number and extends_saved is False))
                if conflict:
                    self.db.execute("INSERT OR REPLACE INTO meta VALUES ('conflict',X'01')")
                    self.db.execute('COMMIT');raise Reject('STATE_CONFLICT')
                if point.number>old.number:require(extends_saved is True,'STATE_UNAVAILABLE')
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('checkpoint',?)",(point.encode(),))
            self.db.execute('COMMIT');self._expected=point
        except BaseException:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise

    def remember_request(self,source,destination,message,request_hash,plaintext):
        require(self._expected is not _UNSET and source==self.local_nft,'STATE_UNAVAILABLE')
        require(digest(plaintext)==request_hash,'INVALID_PAYLOAD')
        args=(uint(source,32),uint(destination,32),fixed(message,32),fixed(request_hash,32),plaintext)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            require(self.saved_checkpoint()==self._expected,'STATE_UNAVAILABLE')
            old=self.db.execute('SELECT destination,request,plaintext FROM requests WHERE source=? AND message=?',
                                (args[0],message)).fetchone()
            require(old is None or old==(args[1],request_hash,plaintext),'MESSAGE_CONFLICT')
            if old is None:
                pending=self.db.execute('''SELECT count(*) FROM requests q LEFT JOIN receipts r
                  ON q.source=r.source AND q.message=r.message WHERE r.phase IS NULL OR r.phase<>2''').fetchone()[0]
                require(pending<64,'POLICY_DENIED')
            self.db.execute('INSERT OR IGNORE INTO requests VALUES (?,?,?,?,?)',args)
            self.db.execute('COMMIT')
        except BaseException:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise
