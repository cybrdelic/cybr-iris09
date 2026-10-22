"""Actual loopback/native-render smoke; running this file uses native OpenGL.

The HTTP client and server control use the standard library. Pillow decodes
actual PNG pixels; byte hashes alone are not accepted as changed-image proof.
"""
import argparse
import base64
import hashlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('serve_native', ROOT/'tools/serve_native.py')
preview=importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


def require(value, message):
    if not value:raise RuntimeError(message)


def request_frame(server, state, timeout):
    connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=timeout+10)
    try:
        connection.request('POST','/api/render',body=json.dumps(state).encode('utf-8'),
                           headers={'Origin':server.origin,'Content-Type':'application/json'})
        response=connection.getresponse()
        payload=response.read(6*1024*1024+1)
        require(len(payload)<=6*1024*1024,'Response exceeds the bounded PNG envelope')
        require(response.status==200,'Native HTTP render failed with status '+str(response.status))
        result=json.loads(payload)
        require(result['state']==state and result['requestId']==state['requestId'],'Completed request state differs')
        require(result['nativeReport']['completed'] is True and result['nativeReport']['finite'] is True,'Native report did not confirm completion')
        return result
    finally:connection.close()


def run(output, timeout):
    from PIL import Image
    names=['first.png','changed.png','http-smoke.json']
    if any((output/name).exists() for name in names):raise ValueError('Refusing to overwrite existing smoke artifacts')
    renderer=preview.NativeRenderer(timeout);server=preview.PreviewServer(renderer=renderer)
    serving=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True)
    serving.start();started=time.monotonic();evidence=[];pixels=[]
    states=[{**preview.DEFAULTS,'drag':[0,0],'requestId':1},
            {**preview.DEFAULTS,'time':5,'drag':[18,-9],'scroll':.25,'requestId':2}]
    try:
        for name,state in zip(names,states):
            result=request_frame(server,state,timeout)
            png=base64.b64decode(result.pop('png'),validate=True)
            with Image.open(io.BytesIO(png)) as image:
                require(image.format=='PNG' and image.size==(160,90),'Actual PNG resolution differs')
                rgb=image.convert('RGB');raw=rgb.tobytes()
                require(any(low!=high for low,high in rgb.getextrema()),'Actual native frame is constant')
            pixels.append(raw);output.mkdir(parents=True,exist_ok=True)
            with (output/name).open('xb') as handle:handle.write(png)
            evidence.append({**result,'file':name,'png_sha256':hashlib.sha256(png).hexdigest(),
                             'rgb_sha256':hashlib.sha256(raw).hexdigest(),'rgb_bytes':len(raw)})
            print(json.dumps({'phase':'native-http-frame','state':state,'elapsedMs':result['elapsedMs']}),flush=True)
        changed=sum(pixels[0][i:i+3]!=pixels[1][i:i+3] for i in range(0,len(pixels[0]),3))
        require(changed>0,'Changed inputs did not change decoded native pixels')
    finally:
        server.shutdown();server.server_close();serving.join(timeout=3)
    require(not serving.is_alive() and renderer.process is None,'Preview did not cleanly shut down')
    released=renderer.busy.acquire(blocking=False)
    if released:renderer.busy.release()
    require(released,'Render lock remained held after shutdown')
    report={'passed':True,'renderer_kind':'Native local OpenGL, not browser GPU','scope':'two real HTTP requests;160x90;AA2;changed time/drag/scroll',
            'frames':evidence,'changed_pixels':changed,'clean_shutdown':True,'wall_seconds':time.monotonic()-started,
            'limits':'Bounded still preview; not browser Live or production-performance qualification.'}
    with (output/'http-smoke.json').open('x',encoding='utf-8') as handle:json.dump(report,handle,indent=2,allow_nan=False)
    print(json.dumps({'passed':True,'changed_pixels':changed,'clean_shutdown':True}),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path('test-results/native/http-preview'))
    parser.add_argument('--timeout',type=float,default=45)
    args=parser.parse_args();run(args.out,args.timeout)


if __name__=='__main__':main()
