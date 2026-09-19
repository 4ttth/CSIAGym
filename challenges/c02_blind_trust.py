"""
Web Exploitation 2 — Blind Trust.

Teaching point: string-concatenated SQL. The classic. The login form trusts the
user's input enough to make it part of the query's grammar, so the user gets to
rewrite the question the database is being asked.
"""

import secrets

from . import _common as common

SLUG        = 'blind-trust'
TITLE       = 'Blind Trust'
CATEGORY    = 'Web'
DIFFICULTY  = 'easy'
POINTS      = 150
DYNAMIC_FLAG = True

DESCRIPTION = """
<p>The society's old attendance portal is still running on a server nobody wants
to admit owning. It has exactly one account that matters &mdash;
<code>admin</code> &mdash; and nobody remembers the password.</p>

<p>You do not need the password.</p>

<p><strong>Launch the instance and log in as <code>admin</code> anyway.</strong></p>

<p><em>Hint:</em> the login query is built by gluing your input straight into a
SQL string. What happens if your input contains a quote?</p>
""".strip()


APP_PY = r'''#!/usr/bin/env python3
"""
HAU CSIA attendance portal (legacy).

Stdlib only. Binds $PORT, which the runner allocates per player.
"""

import os
import html
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get('PORT') or os.environ.get('CHAL_PORT') or 8080)
HERE = os.path.dirname(os.path.abspath(__file__))
FLAG_PATH = os.path.join(HERE, 'flag.txt')
DB_PATH = '/tmp/attendance.db'

ADMIN_PASSWORD = '__ADMIN_PASSWORD__'


def read_flag():
    try:
        with open(FLAG_PATH) as fh:
            return fh.read().strip()
    except OSError:
        return 'CSIA{flag_file_missing_tell_an_organiser}'


def init_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)')
    con.executemany(
        'INSERT INTO users (id, username, password) VALUES (?, ?, ?)',
        [
            (1, 'admin', ADMIN_PASSWORD),
            (2, 'jm.reyes', 'letmein2024'),
            (3, 'a.santos', 'attendance!23'),
            (4, 'guest', 'guest'),
        ],
    )
    con.commit()
    con.close()


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>CSIA Attendance Portal</title>
<style>
  body {{ background:#0b0b0d; color:#e6e6e6; font-family:ui-monospace,Menlo,Consolas,monospace;
         display:flex; min-height:100vh; align-items:center; justify-content:center; margin:0; }}
  .card {{ border:2px solid #8b0000; background:#121215; padding:2.2rem 2.6rem; width:30rem; }}
  h1 {{ color:#e02b2b; margin:0 0 1.2rem; letter-spacing:.06em; font-size:1.3rem; }}
  label {{ display:block; font-size:.75rem; text-transform:uppercase; letter-spacing:.14em;
           color:#888; margin:.9rem 0 .3rem; }}
  input {{ width:100%; box-sizing:border-box; background:#000; border:1px solid #444;
           color:#e6e6e6; padding:.6rem; font-family:inherit; }}
  button {{ margin-top:1.4rem; width:100%; background:#8b0000; color:#fff; border:0;
            padding:.7rem; font-family:inherit; font-weight:700; letter-spacing:.1em;
            text-transform:uppercase; cursor:pointer; }}
  .err {{ border-left:3px solid #e02b2b; padding:.5rem .8rem; color:#f0a; margin-top:1rem; }}
  .flag {{ background:#000; border:1px dashed #e02b2b; color:#31d158; padding:.9rem;
           word-break:break-all; margin-top:1rem; }}
  a {{ color:#e02b2b; }}
</style></head>
<body><div class="card">
  <h1>ATTENDANCE PORTAL &mdash; SIGN IN</h1>
  {body}
</div>
<!-- legacy auth. TODO: parameterise this query before anyone notices. -->
</body></html>
"""

FORM = """
  <form method="post" action="/login">
    <label for="u">Username</label>
    <input id="u" name="username" autocomplete="off" autofocus>
    <label for="p">Password</label>
    <input id="p" name="password" type="password" autocomplete="off">
    <button type="submit">Sign in</button>
  </form>
  {message}
"""


class Handler(BaseHTTPRequestHandler):
    server_version = 'AttendancePortal/0.9'

    def log_message(self, fmt, *args):
        pass

    def _send(self, body, code=200):
        payload = PAGE.format(body=body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.split('?')[0] not in ('/', '/index.html'):
            self.send_error(404, 'Not Found')
            return
        self._send(FORM.format(message=''))

    def do_POST(self):
        if self.path.split('?')[0] != '/login':
            self.send_error(404, 'Not Found')
            return

        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length).decode('utf-8', 'replace')
        fields = urllib.parse.parse_qs(raw, keep_blank_values=True)
        username = (fields.get('username') or [''])[0]
        password = (fields.get('password') or [''])[0]

        # The bug, in one line: the input becomes part of the query's grammar.
        query = ("SELECT id, username FROM users "
                 "WHERE username = '" + username + "' AND password = '" + password + "' "
                 "ORDER BY id")

        con = sqlite3.connect(DB_PATH)
        try:
            row = con.execute(query).fetchone()
        except sqlite3.Error as exc:
            con.close()
            self._send(FORM.format(
                message='<div class="err">SQL error: %s</div>' % html.escape(str(exc))))
            return
        con.close()

        if not row:
            self._send(FORM.format(
                message='<div class="err">No such username / password combination.</div>'))
            return

        who = row[1]
        if who == 'admin':
            body = ('<p>Signed in as <strong>admin</strong>. Attendance records unlocked.</p>'
                    '<div class="flag">%s</div>'
                    '<p><a href="/">Sign out</a></p>' % html.escape(read_flag()))
        else:
            body = ('<p>Signed in as <strong>%s</strong>. This account cannot read the '
                    'attendance archive &mdash; you need <code>admin</code>.</p>'
                    '<p><a href="/">Sign out</a></p>' % html.escape(who))
        self._send(body)


if __name__ == '__main__':
    init_db()
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
'''


def build(ctx):
    src = common.fresh_dir(ctx.path('src'))
    app = APP_PY.replace('__ADMIN_PASSWORD__', secrets.token_urlsafe(24))
    common.write(f'{src}/app.py', app)
    common.write(f'{src}/flag.txt', ctx.flag + '\n')
    archive = common.make_targz(src, ctx.path('blind-trust.tar.gz'))
    return {'description': DESCRIPTION, 'web_archive': archive}
