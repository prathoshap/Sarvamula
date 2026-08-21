#!/usr/bin/env python3
"""Dev server for the Bhāgavatam web app — sends no-cache headers so edits to
app.js / app.css / normalize.js / bhagavatam.db always load fresh (python's
http.server sends none, which makes browsers heuristically serve stale assets).

    cd web && python3 serve.py        # http://localhost:8080
"""
import http.server, os, re, socketserver, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080

class NoCache(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.wasm': 'application/wasm',   # streaming WebAssembly compile
                      '.m4a': 'audio/mp4',           # python maps this to audio/mp4a-latm
                      '.mp4': 'video/mp4'}

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    # ── fall back to the box for audio we have not mirrored ───────────────────
    # The full corpus lives on box1 (2 GB and growing); web/audio/ holds only what was
    # pulled for smoke testing. Rather than make the reader's AUDIO_BASE a manual setting,
    # a miss under /audio/ redirects there — so the default base works for every work, and
    # keeps working unchanged once files are mirrored locally or moved to R2.
    BOX = "http://10.32.38.96:8099"

    def _fallback(self):
        rel = self.path.split("?", 1)[0][len("/audio/"):]
        self.send_response(302)
        self.send_header("Location", f"{self.BOX}/{rel}")
        self.end_headers()
        return None

    # ── HTTP Range ────────────────────────────────────────────────────────────
    # SimpleHTTPRequestHandler ignores Range and answers 200 with the whole file, so a
    # browser CANNOT seek inside <audio>: setting currentTime is unsatisfiable and clamps
    # to 0. That made every karaoke line jump to the start of the block. Cloudflare R2
    # serves ranges natively, so this only ever bit the dev server.
    def send_head(self):
        p = self.path.split("?", 1)[0]
        if p.startswith("/audio/") and not os.path.exists(self.translate_path(p)):
            return self._fallback()
        rng = self.headers.get('Range')
        if not rng:
            return super().send_head()
        path = self.translate_path(self.path)
        if os.path.isdir(path) or not os.path.exists(path):
            return super().send_head()
        m = re.match(r'bytes=(\d*)-(\d*)$', rng.strip())
        if not m:
            return super().send_head()
        size = os.path.getsize(path)
        start, end = m.group(1), m.group(2)
        if start == '':                                   # suffix range: last N bytes
            length = min(int(end or 0), size)
            start, end = size - length, size - 1
        else:
            start = int(start)
            end = int(end) if end else size - 1
        if start >= size or start > end:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.end_headers()
            return None
        end = min(end, size - 1)
        f = open(path, 'rb')
        f.seek(start)
        self.send_response(206)
        self.send_header('Content-type', self.guess_type(path))
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(end - start + 1))
        self.end_headers()
        self._range_remaining = end - start + 1
        return f

    def copyfile(self, src, dst):
        n = getattr(self, '_range_remaining', None)
        if n is None:
            return super().copyfile(src, dst)
        self._range_remaining = None
        while n > 0:
            buf = src.read(min(64 * 1024, n))
            if not buf:
                break
            dst.write(buf); n -= len(buf)

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), NoCache) as httpd:
    print(f"Bhāgavatam dev server (no-cache) → http://localhost:{PORT}")
    httpd.serve_forever()
