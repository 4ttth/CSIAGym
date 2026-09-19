"""
Web Exploitation 1 — Cookie Monster.

Teaching point: a cookie is client-side state. Anything the browser stores,
the browser's owner can rewrite. Authorisation decided from a cookie value is
authorisation handed to the attacker.
"""

from . import _common as common

SLUG        = 'cookie-monster'
TITLE       = 'Cookie Monster'
CATEGORY    = 'Web'
DIFFICULTY  = 'easy'
POINTS      = 100
DYNAMIC_FLAG = True   # runner rewrites flag.txt per player on every launch

DESCRIPTION = """
<p>The CSIA GYM vending machine went online last week. It has a members' area
and a staff area, and the staff area is where the good snacks live.</p>

<p>The developer swears the staff area is locked down. The developer has also
never opened their browser's developer tools.</p>

<p><strong>Launch the instance, open the site, and get yourself into the staff
area.</strong></p>

<p><em>Hint:</em> press <code>F12</code>, then look at
<code>Application &rarr; Cookies</code> (Chrome / Edge) or
<code>Storage &rarr; Cookies</code> (Firefox).</p>
""".strip()


APP_PY = r'''#!/usr/bin/env python3
"""
CSIA GYM Vending — staff portal.

Runs on the stdlib only so the container needs no pip install at launch.
Binds the port the runner allocated, handed over in $PORT.
"""

import os
import html
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get('PORT') or os.environ.get('CHAL_PORT') or 8080)
FLAG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flag.txt')

# TODO(dev): swap this for a signed session before we ship. -- jm
ROLE_COOKIE = 'role'


def read_flag():
    try:
        with open(FLAG_PATH) as fh:
            return fh.read().strip()
    except OSError:
        return 'CSIA{flag_file_missing_tell_an_organiser}'


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>CSIA GYM Vending</title>
<style>
  body {{ background:#0b0b0d; color:#e6e6e6; font-family:ui-monospace,Menlo,Consolas,monospace;
         display:flex; min-height:100vh; align-items:center; justify-content:center; margin:0; }}
  .card {{ border:2px solid #8b0000; background:#121215; padding:2.2rem 2.6rem; max-width:34rem; }}
  h1 {{ color:#e02b2b; margin:0 0 .4rem; letter-spacing:.06em; }}
  .tag {{ display:inline-block; border:1px solid #444; padding:.15rem .6rem; font-size:.75rem;
          text-transform:uppercase; letter-spacing:.12em; color:#999; }}
  .flag {{ background:#000; border:1px dashed #e02b2b; color:#31d158; padding:.9rem; word-break:break-all; }}
  a {{ color:#e02b2b; }}
  ul {{ line-height:1.7; }}
</style></head>
<body><div class="card">
  <h1>CSIA GYM VENDING</h1>
  <div class="tag">session role: {role}</div>
  {body}
</div>
<!-- staff area is gated on the role cookie. members get "guest", we get "admin". -->
</body></html>
"""

MEMBER_BODY = """
  <p>Welcome back, member. Here is what you may purchase:</p>
  <ul><li>Instant coffee (lukewarm)</li><li>Biscuits (2021 vintage)</li><li>Tap water</li></ul>
  <p style="color:#888">The staff shelf is not available to your account.</p>
"""

STAFF_BODY = """
  <p>Staff shelf unlocked. Take whatever you want, you have earned it.</p>
  <ul><li>Cold brew</li><li>The good biscuits</li><li>The flag</li></ul>
  <div class="flag">{flag}</div>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = 'CSIAVending/1.0'

    def log_message(self, fmt, *args):   # keep the container logs quiet
        pass

    def _role(self):
        raw = self.headers.get('Cookie')
        if not raw:
            return None
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except Exception:
            return None
        morsel = jar.get(ROLE_COOKIE)
        return morsel.value if morsel else None

    def do_GET(self):
        if self.path.split('?')[0] not in ('/', '/index.html'):
            self.send_error(404, 'Not Found')
            return

        role = self._role()
        set_cookie = None
        if role is None:
            role = 'guest'
            set_cookie = '%s=guest; Path=/' % ROLE_COOKIE

        if role == 'admin':
            body = STAFF_BODY.format(flag=html.escape(read_flag()))
        else:
            body = MEMBER_BODY

        payload = PAGE.format(role=html.escape(role), body=body).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        if set_cookie:
            self.send_header('Set-Cookie', set_cookie)
        self.end_headers()
        self.wfile.write(payload)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
'''


def build(ctx):
    src = common.fresh_dir(ctx.path('src'))
    common.write(f'{src}/app.py', APP_PY)
    common.write(f'{src}/flag.txt', ctx.flag + '\n')
    archive = common.make_targz(src, ctx.path('cookie-monster.tar.gz'))
    return {'description': DESCRIPTION, 'web_archive': archive}
