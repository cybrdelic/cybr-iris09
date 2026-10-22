"""Embed the maintained runtime and worker; preserve shader and media payloads."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def build(check=False):
    path = ROOT/'IRIS-09-viewer.html'
    original = path.read_text(encoding='utf-8')
    result = original
    for element, source in [('renderWorker','worker.js'),('viewerRuntime','runtime.js')]:
        code = (ROOT/'viewer'/source).read_text(encoding='utf-8').strip()
        if '</script' in code.lower(): raise ValueError('Embedded JavaScript must not contain a closing script tag')
        pattern = rf'(<script id="{element}"[^>]*>).*?(</script>)'
        result, count = re.subn(pattern,lambda m:m[1]+'\n'+code+'\n'+m[2],result,flags=re.S)
        if count != 1: raise ValueError('Expected exactly one '+element+' embedding')
    if check:
        if result != original: raise SystemExit('Viewer embeddings are stale; run python tools/build_viewer.py')
    else: path.write_text(result,encoding='utf-8',newline='\n')

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--check',action='store_true')
    build(parser.parse_args().check)
