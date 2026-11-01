import json
import unittest
from unittest.mock import Mock
from runners.bcp02.common import Blocked
from runners.bcp02.stand import Stand, NS
from runners.bcp02.linux import Clock


class StandGuards(unittest.TestCase):
    def test_collision_never_creates_or_deletes(self):
        execute=Mock(return_value=json.dumps([{'name':NS['A']}]))
        with self.assertRaisesRegex(Blocked,'collision'):Stand(execute,lambda n:1).create()
        self.assertEqual(execute.call_count,1)

    def test_link_up_requires_both_captures(self):
        execute=Mock()
        for ready in (set(),{'L1'},{'L2'}):
            with self.assertRaises(Blocked):Stand(execute,lambda n:1).up(ready)
        execute.assert_not_called()

    def test_cleanup_requires_archive_and_owned_inode(self):
        execute=Mock();s=Stand(execute,lambda n:5);s.created={NS['A']:4}
        with self.assertRaises(Blocked):s.cleanup(archived=False)
        with self.assertRaisesRegex(Blocked,'replacement'):s.cleanup(archived=True)
        execute.assert_not_called()

    def test_cleanup_refuses_foreign_interface(self):
        execute=Mock(return_value=json.dumps([{'ifname':'unexpected0'}]))
        s=Stand(execute,lambda n:5);s.created={NS['A']:5}
        with self.assertRaisesRegex(Blocked,'foreign'):s.cleanup(archived=True)
        self.assertFalse(any('delete' in c.args[0] for c in execute.call_args_list))

    def test_clock_discontinuity_is_not_trusted(self):
        from unittest.mock import patch
        with patch('time.time',return_value=1010),patch('time.monotonic',return_value=11):
            with self.assertRaises(Blocked):Clock(1000,10).read()


if __name__=='__main__':unittest.main()
