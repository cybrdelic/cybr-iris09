"""Offline integrity checks; do not claim a rendered Live frame."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ViewerTests(unittest.TestCase):
    def test_shader_download_matches_source(self):
        html=(ROOT/'IRIS-09-viewer.html').read_text(encoding='utf-8')
        embedded=json.loads(re.search(r'<script\b[^>]*\bid="shaderSource"[^>]*>(.*?)</script>',html,re.S)[1])
        shaders=list(ROOT.glob('*.glsl'))
        self.assertTrue(any(p.read_text(encoding='utf-8').replace('\r\n','\n')==embedded.replace('\r\n','\n') for p in shaders))

    def test_embeddings_current(self):
        subprocess.run(['python',str(ROOT/'tools/build_viewer.py'),'--check'],check=True)

    def test_javascript_parses(self):
        for name in ['runtime.js','worker.js']:
            subprocess.run(['node','--check',str(ROOT/'viewer'/name)],check=True)

    def test_worker_protocol_without_gpu(self):
        subprocess.run(['node',str(ROOT/'tests/test_worker_protocol.cjs')],check=True)

    def test_preflight_limits_only_observed_stalling_backends(self):
        subprocess.run(['node',str(ROOT/'tests/test_preflight.cjs')],check=True)

if __name__ == '__main__': unittest.main()
