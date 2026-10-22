"""Loopback-only IRIS native OpenGL preview. No browser GPU rendering is used."""
import argparse
import base64
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
BODY_LIMIT = 4096
PNG_LIMIT = 4 * 1024 * 1024
DEFAULTS = dict(width=160, height=90, time=0, drag=[0, 0], scroll=0, samples=2)


class RequestError(ValueError):
    pass


class RenderFailure(RuntimeError):
    pass


class Busy(RenderFailure):
    pass


def validate_state(value):
    if not isinstance(value, dict) or set(value) != {*DEFAULTS, 'requestId'}:
        raise RequestError('Expected only requestId, width, height, time, drag, scroll and samples.')
    for name, low, high in [('width', 1, 640), ('height', 1, 640), ('samples', 1, 2), ('requestId', 0, 2**31-1)]:
        if type(value[name]) is not int or not low <= value[name] <= high:
            raise RequestError(name + ' must be an integer within the documented limits.')
    if value['width'] * value['height'] > 640 * 360:
        raise RequestError('Preview is limited to 230400 pixels; requested dimensions are never reduced.')
    if not isinstance(value['drag'], list) or len(value['drag']) != 2:
        raise RequestError('drag must contain exactly two coordinates.')
    for name, number, low, high in [('time', value['time'], 0, 10), ('scroll', value['scroll'], -2, 2),
                                  ('drag X', value['drag'][0], -8192, 8192), ('drag Y', value['drag'][1], -8192, 8192)]:
        if type(number) not in (int, float) or not low <= number <= high or not math.isfinite(number):
            raise RequestError(name + ' must be finite and within the documented limits.')
    return dict(value, drag=list(value['drag']))


def decode_request(raw):
    def invalid_constant(_):
        raise RequestError('NaN and Infinity are not valid preview inputs.')
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RequestError('Duplicate JSON fields are not accepted.')
            result[key] = value
        return result
    try:
        return validate_state(json.loads(raw.decode('utf-8'), parse_constant=invalid_constant,
                                         object_pairs_hook=unique_object))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise RequestError('Expected a valid UTF-8 JSON object.') from error


def kill_owned(process):
    if process.poll() is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


class NativeRenderer:
    """One directly owned renderer child. No shell, queue, or client-supplied path."""
    def __init__(self, timeout=45):
        if not math.isfinite(timeout) or not 1 <= timeout <= 120:
            raise ValueError('Native timeout must be between 1 and 120 seconds.')
        self.timeout = timeout
        self.busy = threading.Lock()
        self.process_lock = threading.Lock()
        self.process = None
        self.closed = False

    def close(self):
        with self.process_lock:
            self.closed = True
            process = self.process
        if process is not None:
            kill_owned(process)

    def render(self, state):
        state = validate_state(state)
        if not self.busy.acquire(blocking=False):
            raise Busy('Another native frame is rendering. Wait for it to finish; no request was queued.')
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix='iris-preview-') as directory:
                png = Path(directory) / 'frame.png'
                report_path = Path(directory) / 'report.json'
                command = [sys.executable, str(ROOT / 'tools' / 'render_native.py'), '--worker',
                           '--width', str(state['width']), '--height', str(state['height']),
                           '--time', str(state['time']), '--drag', *map(str, state['drag']),
                           '--scroll', str(state['scroll']), '--samples', str(state['samples']),
                           '--output', str(png), '--json', str(report_path), '--timeout', str(self.timeout)]
                with self.process_lock:
                    if self.closed:
                        raise RenderFailure('Native preview is shutting down.')
                    self.process = process = subprocess.Popen(command, cwd=str(ROOT), shell=False,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    try:
                        returncode = process.wait(timeout=self.timeout)
                    except subprocess.TimeoutExpired as error:
                        kill_owned(process)
                        raise RenderFailure('Native rendering exceeded its process deadline. Submitted driver work may still need time to unwind.') from error
                finally:
                    if process.poll() is None:
                        kill_owned(process)
                    with self.process_lock:
                        if self.process is process:
                            self.process = None
                if returncode != 0:
                    raise RenderFailure('Native renderer failed. Check requirements-native.txt and native OpenGL support with tools/render_native.py; no replacement frame was used.')
                if not report_path.is_file() or report_path.stat().st_size > 256 * 1024:
                    raise RenderFailure('Native renderer did not produce a valid completion report.')
                try:
                    report = json.loads(report_path.read_text(encoding='utf-8'))
                except (OSError, ValueError) as error:
                    raise RenderFailure('Native completion report could not be read.') from error
                if report.get('completed') is not True or report.get('finite') is not True or report.get('resolution') != [state['width'], state['height']]:
                    raise RenderFailure('Native renderer did not confirm a finite frame at the requested size.')
                expected = {'time':state['time'], 'drag':state['drag'], 'scroll':state['scroll'], 'AA':state['samples'], 'camera_samples':state['samples']**2}
                if any(report.get(key) != value for key, value in expected.items()):
                    raise RenderFailure('Native completion inputs do not match the requested camera and sampling.')
                if not png.is_file() or not 33 <= png.stat().st_size <= PNG_LIMIT:
                    raise RenderFailure('Native renderer did not produce a bounded PNG frame.')
                image = png.read_bytes()
                if image[:8] != b'\x89PNG\r\n\x1a\n' or image[12:16] != b'IHDR' or struct.unpack('>II', image[16:24]) != (state['width'], state['height']):
                    raise RenderFailure('Native PNG dimensions do not match the request.')
                return {'requestId': state['requestId'], 'state': state,
                        'renderer': 'Native preview rendered by local OpenGL, not browser GPU',
                        'elapsedMs': (time.monotonic()-started)*1000,
                        'nativeReport': {key:report[key] for key in ('renderer_kind','platform','backend','renderer','version','resolution','time','drag','scroll','AA','camera_samples','compile_ms','render_ms','total_ms','finite','completed','archive_normalized_text_sha256') if key in report},
                        'png': base64.b64encode(image).decode('ascii')}
        finally:
            self.busy.release()


class PreviewServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = False
    def __init__(self, port=0, renderer=None):
        self.renderer = renderer or NativeRenderer()
        super().__init__(('127.0.0.1', port), PreviewHandler)
        self.origin = 'http://127.0.0.1:' + str(self.server_port)
    def server_close(self):
        self.renderer.close()
        super().server_close()


class PreviewHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'IRISNativePreview'
    sys_version = ''
    def setup(self):
        super().setup()
        self.connection.settimeout(5)
    def log_message(self, *args):
        pass
    def send_data(self, code, payload, content_type='application/json; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
    def reply(self, code, value):
        self.send_data(code, json.dumps(value, allow_nan=False).encode('utf-8'))
    def allowed(self, require_origin=False):
        expected = self.server.origin
        hosts = self.headers.get_all('Host', [])
        origins = self.headers.get_all('Origin', [])
        if hosts != [expected.removeprefix('http://')]:
            self.reply(403, {'error':'This preview accepts only its exact loopback Host.'}); return False
        if (require_origin and origins != [expected]) or (origins and origins != [expected]):
            self.reply(403, {'error':'Same-origin requests are required.'}); return False
        if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
            self.reply(403, {'error':'Cross-site requests are not accepted.'}); return False
        return True
    def do_GET(self):
        if not self.allowed(): return
        assets = {'/': ('preview.html', 'text/html; charset=utf-8'), '/preview.js': ('preview.js', 'text/javascript; charset=utf-8')}
        if self.path in assets:
            name, content_type = assets[self.path]
            self.send_data(200, (ROOT / 'tools' / 'iris_native' / name).read_bytes(), content_type)
        elif self.path == '/api/info':
            self.reply(200, {'renderer':'Native preview rendered by local OpenGL, not browser GPU',
                            'defaults':DEFAULTS, 'timeoutSeconds':self.server.renderer.timeout,
                            'maxDimension':640, 'maxPixels':640*360})
        elif self.path == '/favicon.ico': self.send_data(204, b'')
        else: self.reply(404, {'error':'Unknown preview route.'})
    def do_POST(self):
        if not self.allowed(require_origin=True): return
        if self.path != '/api/render':
            self.reply(404, {'error':'Unknown preview route.'}); return
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') is not None or len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            self.reply(400, {'error':'One numeric Content-Length and no transfer encoding are required.'}); return
        if len(lengths[0]) > 6:
            self.reply(413, {'error':'Request body must contain 1 to 4096 bytes.'}); return
        length = int(lengths[0])
        if not 1 <= length <= BODY_LIMIT:
            self.reply(413, {'error':'Request body must contain 1 to 4096 bytes.'}); return
        if self.headers.get_content_type() != 'application/json':
            self.reply(415, {'error':'Content-Type must be application/json.'}); return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length: raise RequestError('Incomplete request body.')
            state = decode_request(raw)
        except (RequestError, TimeoutError) as error:
            self.reply(400, {'error':str(error)}); return
        try:
            self.reply(200, self.server.renderer.render(state))
        except Busy as error: self.reply(409, {'error':str(error)})
        except RenderFailure as error: self.reply(503, {'error':str(error)})
        except Exception: self.reply(500, {'error':'Native preview failed; no replacement frame was used.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0, help='Loopback port; zero selects an available port.')
    parser.add_argument('--timeout', type=float, default=45, help='Owned render-child deadline, 1-120 seconds.')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535: parser.error('Port must be between 0 and 65535.')
    try: renderer = NativeRenderer(args.timeout)
    except ValueError as error: parser.error(str(error))
    server = PreviewServer(args.port, renderer)
    print('Native preview rendered by local OpenGL, not browser GPU: ' + server.origin, flush=True)
    print('One frame at a time. Stop with Ctrl+C. No browser is opened automatically.', flush=True)
    try: server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__':
    main()
