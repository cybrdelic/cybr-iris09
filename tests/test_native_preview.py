"""CPU HTTP/process contracts with mocked frames; not GPU execution evidence."""
import base64
import http.client
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('serve_native', ROOT/'tools/serve_native.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


def state(**changes):
    return {**preview.DEFAULTS, 'drag':[0, 0], 'requestId':1, **changes}


def png(width=160, height=90):
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))+chunk(b'IDAT', zlib.compress((b'\0'+bytes(width*3))*height))+chunk(b'IEND', b'')


class FakeRenderer:
    timeout = 45
    def __init__(self): self.calls=[]; self.closed=False; self.fail=None
    def render(self, value):
        self.calls.append(value)
        if self.fail: raise self.fail
        return {'requestId':value['requestId'], 'state':value, 'elapsedMs':1,
                'renderer':'MOCK CPU PROTOCOL FIXTURE - NOT GPU EVIDENCE', 'png':base64.b64encode(png(value['width'],value['height'])).decode()}
    def close(self): self.closed=True


class Inputs(unittest.TestCase):
    def test_valid_inputs_keep_exact_requested_size_and_sampling(self):
        item=state(width=320, height=180, time=5.25, scroll=-.5, samples=1)
        self.assertEqual(preview.decode_request(json.dumps(item).encode()), item)
    def test_nonfinite_boolean_unknown_duplicate_and_bounds_rejected(self):
        invalid=[state(width=True),state(samples=True),state(width=0),state(height=641),state(width=640,height=640),
                 state(samples=3),state(time=10**400),state(time=float('nan')),state(scroll=float('inf')),state(time=10.1),
                 state(scroll=-2.1),state(drag=[8193,0]),state(drag=[0]),state(drag=[False,0]),state(requestId=-1),state(path='x')]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(preview.RequestError):
                preview.decode_request(json.dumps(item).encode())
        for raw in (b'[]', b'null', b'{}', b'\xff', b'{', b'{"width":1,"width":2}', b'['*1100+b']'*1100):
            with self.subTest(raw=raw), self.assertRaises(preview.RequestError): preview.decode_request(raw)
    def test_timeout_is_finite_and_bounded(self):
        for timeout in (float('nan'),float('inf'),0,121):
            with self.assertRaises(ValueError): preview.NativeRenderer(timeout)


class HTTPContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer=FakeRenderer(); cls.server=preview.PreviewServer(renderer=cls.renderer)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
    def setUp(self): self.renderer.calls.clear();self.renderer.fail=None
    def request(self, method='POST', path='/api/render', body=None, headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        hdr={'Origin':self.server.origin,'Content-Type':'application/json'}
        if headers: hdr.update(headers)
        try:
            connection.request(method,path,body=json.dumps(state()).encode() if body is None and method=='POST' else body,headers=hdr)
            response=connection.getresponse();return response.status,dict(response.getheaders()),response.read()
        finally: connection.close()
    def test_loopback_assets_and_honest_label(self):
        self.assertEqual(self.server.server_address[0],'127.0.0.1')
        code,headers,body=self.request('GET','/')
        self.assertEqual(code,200);self.assertIn(b'not browser GPU rendering',body)
        self.assertEqual(headers['X-Frame-Options'],'DENY');self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.assertIn("connect-src 'self'",headers['Content-Security-Policy'])
    def test_success_returns_exact_state_and_png(self):
        desired=state(time=5,drag=[14,-7],scroll=.3,samples=2)
        code,_,body=self.request(body=json.dumps(desired).encode())
        result=json.loads(body);self.assertEqual(code,200);self.assertEqual(result['state'],desired)
        self.assertEqual(base64.b64decode(result['png']),png());self.assertEqual(len(self.renderer.calls),1)
    def test_host_origin_and_cross_site_reject_before_render(self):
        for headers in ({'Host':'attacker.example'}, {'Host':'localhost:'+str(self.server.server_port)},
                        {'Origin':'http://attacker.example'}, {'Origin':'null'}, {'Sec-Fetch-Site':'cross-site'}):
            with self.subTest(headers=headers): self.assertEqual(self.request(headers=headers)[0],403)
        self.assertFalse(self.renderer.calls)
    def test_missing_origin_rejected(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            conn.request('POST','/api/render',body=b'{}',headers={'Content-Type':'application/json'})
            response=conn.getresponse();self.assertEqual(response.status,403);response.read()
        finally: conn.close()
        self.assertFalse(self.renderer.calls)
    def test_body_type_size_encoding_and_routes_are_bounded(self):
        for body,headers,code in [(b'x'*4097,{},413),(b'{}',{'Content-Type':'text/plain'},415),
                                  (b'{}',{'Transfer-Encoding':'chunked'},400),(b'{}',{'Content-Length':'9'*5000},413),(b'\xff',{},400),
                                  (b'{"time":NaN}',{},400)]:
            with self.subTest(code=code):self.assertEqual(self.request(body=body,headers=headers)[0],code)
        for path in ('/../requirements-native.txt','/%2e%2e/requirements-native.txt','/api/render?path=x','/tools/render_native.py'):
            with self.subTest(path=path):self.assertEqual(self.request('GET',path)[0],404)
        self.assertFalse(self.renderer.calls)
    def test_busy_and_failure_do_not_claim_frame_success(self):
        self.renderer.fail=preview.Busy('busy');self.assertEqual(self.request()[0],409)
        self.renderer.fail=preview.RenderFailure('failed');code,_,body=self.request()
        self.assertEqual(code,503);self.assertNotIn('png',json.loads(body))


class FakeProcess:
    def __init__(self, timeout=False): self.returncode=None;self.timeout=timeout;self.kills=0
    def wait(self, timeout=None):
        if self.timeout and self.returncode is None: raise subprocess.TimeoutExpired('owned child',timeout)
        if self.returncode is None:self.returncode=0
        return self.returncode
    def poll(self):return self.returncode
    def kill(self):self.kills+=1;self.returncode=-9


class ProcessContracts(unittest.TestCase):
    def factory(self, report_changes=None, wrong_size=False):
        def launch(command, **kwargs):
            self.command=command;self.kwargs=kwargs
            out=Path(command[command.index('--output')+1]);rep=Path(command[command.index('--json')+1])
            get=lambda name:command[command.index('--'+name)+1]
            width,height=int(get('width')),int(get('height'));drag=command[command.index('--drag')+1:command.index('--drag')+3]
            report={'completed':True,'finite':True,'resolution':[width,height],'time':float(get('time')),
                    'drag':list(map(float,drag)),'scroll':float(get('scroll')),'AA':int(get('samples')),'camera_samples':int(get('samples'))**2}
            report['private_path']='MUST_NOT_RETURN';report['renderer']='mock fixture';report.update(report_changes or {});rep.write_text(json.dumps(report));out.write_bytes(png(1 if wrong_size else width,height))
            return FakeProcess()
        return launch
    def test_direct_owned_worker_fixed_paths_exact_inputs_and_temp_cleanup(self):
        renderer=preview.NativeRenderer(7)
        with patch.object(preview.subprocess,'Popen',side_effect=self.factory()):
            result=renderer.render(state(time=5,drag=[4,-3],scroll=.2))
        self.assertEqual(result['state']['drag'],[4,-3]);self.assertIn('--worker',self.command)
        self.assertEqual(result['nativeReport']['renderer'],'mock fixture');self.assertNotIn('private_path',result['nativeReport'])
        self.assertEqual(self.command[0],sys.executable);self.assertFalse(self.kwargs['shell'])
        self.assertFalse(Path(self.command[self.command.index('--output')+1]).exists())
        self.assertIsNone(renderer.process)
    def test_invalid_completion_and_size_never_deliver_png(self):
        for changes,bad_size in [({'finite':False},False),({'completed':False},False),({'AA':1},False),({'time':9},False),({},True)]:
            with self.subTest(changes=changes,bad_size=bad_size),patch.object(preview.subprocess,'Popen',side_effect=self.factory(changes,bad_size)):
                with self.assertRaises(preview.RenderFailure):preview.NativeRenderer().render(state())
    def test_timeout_kills_only_owned_child_and_releases_busy(self):
        renderer=preview.NativeRenderer(1);process=FakeProcess(timeout=True)
        with patch.object(preview.subprocess,'Popen',return_value=process):
            with self.assertRaisesRegex(preview.RenderFailure,'deadline'):renderer.render(state())
        self.assertEqual(process.kills,1);self.assertIsNone(renderer.process)
        self.assertTrue(renderer.busy.acquire(blocking=False));renderer.busy.release()
    def test_busy_rejects_without_process_or_queue(self):
        renderer=preview.NativeRenderer();renderer.busy.acquire()
        try:
            with patch.object(preview.subprocess,'Popen') as launch:
                with self.assertRaises(preview.Busy):renderer.render(state())
                launch.assert_not_called()
        finally:renderer.busy.release()
    def test_shutdown_kills_owned_process_and_prevents_new_launch(self):
        renderer=preview.NativeRenderer();owned=FakeProcess();renderer.process=owned;renderer.close()
        self.assertEqual(owned.kills,1)
        with patch.object(preview.subprocess,'Popen') as launch:
            with self.assertRaisesRegex(preview.RenderFailure,'shutting down'):renderer.render(state())
            launch.assert_not_called()

    def test_http_shutdown_joins_active_handler_and_removes_temporary_outputs(self):
        entered=threading.Event();released=threading.Event();paths=[];result=[]
        class BlockingProcess(FakeProcess):
            def wait(self, timeout=None):
                entered.set()
                if not released.wait(timeout):raise subprocess.TimeoutExpired('mock owned renderer',timeout)
                return self.returncode
            def kill(self):
                super().kill();released.set()
        owned=BlockingProcess()
        def launch(command, **kwargs):
            paths.append(Path(command[command.index('--output')+1]).parent)
            return owned
        renderer=preview.NativeRenderer(10);server=preview.PreviewServer(renderer=renderer)
        serving=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);serving.start()
        def call():
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            try:
                conn.request('POST','/api/render',body=json.dumps(state()),headers={'Origin':server.origin,'Content-Type':'application/json'})
                response=conn.getresponse();result.append(response.status);response.read()
            finally:conn.close()
        request=threading.Thread(target=call,daemon=True)
        with patch.object(preview.subprocess,'Popen',side_effect=launch):
            request.start()
            try:
                self.assertTrue(entered.wait(2),'Handler did not reach the mocked owned renderer')
                self.assertTrue(paths[0].exists())
                server.shutdown();server.server_close()
                self.assertFalse(paths[0].exists(),'server_close returned before request-owned temporary cleanup')
                self.assertFalse(server.daemon_threads);self.assertTrue(server.block_on_close)
            finally:
                released.set();server.shutdown();server.server_close();request.join(timeout=3);serving.join(timeout=3)
        self.assertEqual(result,[503]);self.assertEqual(owned.kills,1)
        self.assertFalse(request.is_alive());self.assertIsNone(renderer.process)


if __name__=='__main__':unittest.main(verbosity=2)
