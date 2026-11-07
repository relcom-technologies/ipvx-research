import errno
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
from bcp.wire import Reject, decode_ethernet
from runners.bcp02.cli import main
from runners.bcp02.common import Blocked, private_json
from runners.bcp02.pcap import Writer
from runners.bcp02.rehearsal import MARK, SIZES, rehearse, verify_capture, wrap
from runners.bcp02.stand import Stand, actor_parent, reachable
from runners.bcp02.transport import PacketPort
from runners.bcp02.verifier import evaluate

BODY={size:MARK+bytes(size-14-len(MARK)) for size in SIZES}


def port_api(pending=0):
    api=Mock(AF_PACKET=17,SOCK_RAW=3,SOL_SOCKET=1,SO_RCVBUF=8,SO_ERROR=4,MSG_TRUNC=32)
    api.htons.side_effect=lambda n:n;api.if_nametoindex.return_value=7
    api.socket.return_value.getsockopt.return_value=pending
    return api


def ioctl(index):
    return lambda fd,request,buffer:buffer[:16]+index.to_bytes(4,'little')+buffer[20:]


class KernelContact(unittest.TestCase):
    def test_fresh_host_without_run_netns_prints_nothing(self):
        class Reached(Exception):pass
        execute=Mock(side_effect=['',Reached()])
        with self.assertRaises(Reached):Stand(execute,lambda n:1).create()
        self.assertEqual(execute.call_args_list[1].args[0][:3],['ip','netns','add'])

    def test_capture_on_a_down_link_clears_the_pending_error(self):
        api=port_api(errno.ENETDOWN)
        PacketPort('a0',capture=True,api=api,ioctl=ioctl(7))
        api.socket.return_value.getsockopt.assert_called_once_with(1,4)

    def test_only_a_capture_may_start_on_a_down_link(self):
        api=port_api(errno.ENETDOWN)
        with self.assertRaisesRegex(Blocked,'bind error'):PacketPort('a0',api=api,ioctl=ioctl(7))
        api.socket.return_value.close.assert_called_once()

    def test_other_bind_errors_stop_a_capture(self):
        with self.assertRaisesRegex(Blocked,'bind error'):
            PacketPort('a0',capture=True,api=port_api(errno.ENODEV),ioctl=ioctl(7))

    def test_traffic_checks_never_ask_glibc_for_a_new_socket(self):
        api=port_api();raw=wrap('a0',BODY[60])
        def receive(buffers,*args):
            buffers[0][:len(raw)]=raw;return len(raw),[],0,('a0',0,0,1,b'')
        api.socket.return_value.recvmsg_into.side_effect=receive
        api.socket.return_value.send.return_value=len(raw)
        port=PacketPort('a0',api=api,ioctl=ioctl(7))
        self.assertEqual(port.recv(),raw);port.send(raw)
        api.if_nametoindex.assert_called_once_with('a0')

    def test_a_replaced_interface_stops_traffic(self):
        api=port_api();raw=wrap('a0',BODY[60])
        def receive(buffers,*args):
            buffers[0][:len(raw)]=raw;return len(raw),[],0,('a0',0,0,1,b'')
        api.socket.return_value.recvmsg_into.side_effect=receive
        port=PacketPort('a0',api=api,ioctl=ioctl(8))
        with self.assertRaisesRegex(Blocked,'RX interface'):port.recv()
        with self.assertRaisesRegex(Blocked,'TX interface'):port.send(raw)


class ActorPaths(unittest.TestCase):
    def test_actor_parent_lets_actors_pass_but_not_list(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(actor_parent(Path(d,'run')).stat().st_mode&0o777,0o711)
            with self.assertRaises(FileExistsError):actor_parent(Path(d,'run'))

    def test_output_under_a_closed_directory_is_refused(self):
        modes={'/':0o755,'/srv':0o700,'/srv/ipvx':0o755}
        def status(path,**kwargs):return Mock(st_mode=stat.S_IFDIR|modes[str(path)])
        with patch('pathlib.Path.resolve',lambda p,**k:p),patch('pathlib.Path.stat',status):
            with self.assertRaisesRegex(Blocked,'searchable'):reachable(Path('/srv/ipvx/run'))
            modes['/srv']=0o711;reachable(Path('/srv/ipvx/run'))


class Rehearsal(unittest.TestCase):
    def capture(self,folder,frames,drops=0,packets=None,error=None):
        with open(Path(folder)/'capture.pcap','xb') as f:
            writer=Writer(f)
            for raw in frames:writer.append(raw,1000.5)
        private_json(Path(folder)/'capture-statistics.json',dict(error=error,statistics=[dict(
            packets=len(frames) if packets is None else packets,drops=drops,ifindex=7,unfiltered=True)]))

    def good(self):
        return [wrap(p,BODY[s]) for p in ('a0','r0') for s in SIZES]

    def test_refuses_without_root_on_linux_before_touching_anything(self):
        with tempfile.TemporaryDirectory() as d,patch('runners.bcp02.rehearsal.Stand') as stand:
            target=Path(d,'out')
            with patch('sys.platform','darwin'),self.assertRaisesRegex(Blocked,'root'):rehearse(target)
            with patch('sys.platform','linux'),patch('os.geteuid',return_value=1000),self.assertRaisesRegex(Blocked,'root'):rehearse(target)
            stand.assert_not_called();self.assertFalse(target.exists())

    def test_frames_are_synthetic_and_cannot_be_read_as_bcp(self):
        for size,body in BODY.items():
            raw=wrap('a0',body);self.assertEqual((len(raw),raw[12:14]),(size,b'\x88\xb5'))
            with self.assertRaises(Reject):decode_ethernet(raw,bytes(32))

    def test_capture_passes_only_on_the_exact_frames_without_drops(self):
        with tempfile.TemporaryDirectory() as d:
            self.capture(d,self.good());self.assertEqual(verify_capture(d),dict(frames=4,drops=0))
        foreign=wrap('a0',BODY[60])[:14]+bytes(46)
        for frames,kwargs,reason in ((self.good()[:3],{},'frame set'),(self.good()+[self.good()[0]],{},'frame set'),
                                     (self.good()[:3]+[foreign],{},'foreign'),(self.good(),{'drops':1},'drops'),
                                     (self.good(),{'packets':5},'drops'),(self.good(),{'error':'OSError'},'error')):
            with tempfile.TemporaryDirectory() as d,self.subTest(reason=reason,kwargs=kwargs):
                self.capture(d,frames,**kwargs)
                with self.assertRaisesRegex(Blocked,reason):verify_capture(d)

    def test_a_rehearsal_directory_never_reads_as_a_run(self):
        with tempfile.TemporaryDirectory() as d:
            private_json(Path(d,'rehearsal.json'),dict(outcome='REHEARSAL_PASS'))
            self.assertEqual(evaluate(d)['outcome'],'INCONCLUSIVE')

    def test_command_touches_no_permit_or_dataset(self):
        report=dict(outcome='REHEARSAL_PASS')
        with patch('sys.argv',['cli','rehearse','--output','/nonexistent/out']),\
             patch('runners.bcp02.rehearsal.rehearse',return_value=report) as run,\
             patch('runners.bcp02.cli.authorize',side_effect=AssertionError('no permit')),\
             patch('builtins.print'),self.assertRaises(SystemExit) as stop:
            main()
        self.assertEqual(stop.exception.code,0);run.assert_called_once()

    def test_command_reports_failure_and_refusal(self):
        for outcome,code in (({'outcome':'REHEARSAL_FAIL'},1),(Blocked('root on a Linux host required'),2)):
            with self.subTest(code=code),patch('sys.argv',['cli','rehearse','--output','/nonexistent/out']),\
                 patch('runners.bcp02.rehearsal.rehearse',side_effect=[outcome]),\
                 patch('builtins.print'),self.assertRaises(SystemExit) as stop:
                main()
            self.assertEqual(stop.exception.code,code)


if __name__=='__main__':unittest.main()
