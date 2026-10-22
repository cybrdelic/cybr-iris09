"""Bounded real browser checks. A Film fallback is not a successful Live render."""
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json
import threading
import os
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'test-results';output.mkdir(exist_ok=True)
server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
results=[]
try:
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(**({'channel':os.environ['CYBR_BROWSER_CHANNEL']} if os.environ.get('CYBR_BROWSER_CHANNEL') else {}))
        page=browser.new_page(viewport={'width':1280,'height':720})
        page.goto(f'http://127.0.0.1:{server.server_port}/IRIS-09-viewer.html')
        page.locator('#film').evaluate('(video) => video.pause()')
        for width,height in [(1280,720),(390,844),(844,390)]:
            page.set_viewport_size({'width':width,'height':height})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.evaluate('document.body.dataset.mode') == 'film'
            page.screenshot(path=str(output/f'film-{width}x{height}.png'),timeout=15000)
        page.locator('#liveMode').click(timeout=5000)
        # The main-thread mode remains queryable during preflight/compilation.
        assert page.evaluate('document.body.dataset.mode') in ['live','film']
        page.wait_for_function("window.irisDiagnostics.frames > 0 || window.irisDiagnostics.lastError !== null",timeout=45000)
        results.append(page.evaluate('window.irisDiagnostics'))
        assert page.evaluate("document.body.dataset.mode === 'film' || window.irisDiagnostics.frames > 0")
        page.locator('#filmMode').click(timeout=5000)
        page.screenshot(path=str(output/'after-live.png'),timeout=15000)
        browser.close()
finally:
    server.shutdown()
    (output/'browser.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
