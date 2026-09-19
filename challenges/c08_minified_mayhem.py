"""
Reverse Engineering 2 — Minified Mayhem.

Teaching point: client-side JavaScript is shipped to the attacker by design.
Obfuscation raises the reading cost and nothing else — and the same console
that renders the page will happily run the author's own decode routine for you.

This one is deliberately browser-only so the half of the room without a working
Kali VM is not locked out of the category.
"""

import base64
import secrets

from . import _common as common

SLUG        = 'minified-mayhem'
TITLE       = 'Minified Mayhem'
CATEGORY    = 'Reverse Engineering'
DIFFICULTY  = 'easy'
POINTS      = 150
DYNAMIC_FLAG = False

DESCRIPTION = """
<p>A single-page "vault" that runs entirely in your browser. No server, no
network, no excuses &mdash; everything it needs to check your passphrase was
shipped to you inside the file.</p>

<p>Download <code>vault.html</code>, open it in a browser, and get the vault
open.</p>

<p><em>Hints:</em></p>
<ul>
  <li>View source (<code>Ctrl+U</code>). The variable names are noise; the
      data is not.</li>
  <li>Open the console (<code>F12</code> &rarr; Console) on the page itself and
      evaluate the script's own helpers. Whatever it can decode, you can
      decode.</li>
  <li>The passphrase is not stored in plain text, but it is stored
      <em>reversibly</em>. Count the layers.</li>
</ul>

<p>No terminal required. This one is pure browser.</p>
""".strip()


_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>VAULT</title>
<style>
  body{background:#0b0b0d;color:#e6e6e6;font-family:ui-monospace,Menlo,Consolas,monospace;
       display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
  .card{border:2px solid #8b0000;background:#121215;padding:2.2rem 2.6rem;width:32rem}
  h1{color:#e02b2b;margin:0 0 .3rem;letter-spacing:.1em;font-size:1.4rem}
  p.sub{color:#777;margin:0 0 1.4rem;font-size:.8rem;letter-spacing:.08em;text-transform:uppercase}
  input{width:100%;box-sizing:border-box;background:#000;border:1px solid #444;color:#e6e6e6;
        padding:.65rem;font-family:inherit}
  button{margin-top:1rem;width:100%;background:#8b0000;color:#fff;border:0;padding:.7rem;
         font-family:inherit;font-weight:700;letter-spacing:.1em;text-transform:uppercase;cursor:pointer}
  #out{margin-top:1.2rem;padding:.9rem;border:1px dashed #333;color:#888;word-break:break-all;min-height:1.2rem}
  #out.ok{border-color:#e02b2b;color:#31d158;background:#000}
  #out.no{border-color:#8b0000;color:#f06}
</style>
</head>
<body>
<div class="card">
  <h1>THE VAULT</h1>
  <p class="sub">client-side authentication &middot; build __BUILD__</p>
  <input id="pw" placeholder="passphrase" autocomplete="off" autofocus>
  <button id="go">Open</button>
  <div id="out">locked</div>
</div>
<script>
var _0x__ID__=[__ARRAY__];
function _0x__ID__d(_0xa){return atob(_0x__ID__[_0xa]);}
(function(){
var _0xq=function(_0xs){return document['getElementById'](_0xs);};
var _0xv=[__PAYLOAD__];
function _0xr(_0xk){var _0xo='';for(var _0xi=0;_0xi<_0xv['length'];_0xi++){
_0xo+=String['fromCharCode'](_0xv[_0xi]^_0xk['charCodeAt'](_0xi%_0xk['length']));}return _0xo;}
function _0xw(_0xt,_0xc){var _0xe=_0xq(_0x__ID__d(2));_0xe['textContent']=_0xt;_0xe['className']=_0xc;}
_0xq(_0x__ID__d(3))['onclick']=function(){
var _0xp=_0xq(_0x__ID__d(4))['value'];
if(btoa(_0xp)===_0x__ID__d(0)){_0xw(_0xr(_0xp),_0x__ID__d(5));}else{_0xw(_0x__ID__d(1),_0x__ID__d(6));}};
_0xq(_0x__ID__d(4))['addEventListener']('keydown',function(_0xev){
if(_0xev['key']==='Enter'){_0xq(_0x__ID__d(3))['click']();}});
})();
</script>
</body>
</html>
'''


def build(ctx):
    adjectives = ['brass', 'hollow', 'velvet', 'crooked', 'amber', 'silent']
    nouns = ['lighthouse', 'turnstile', 'metronome', 'anchor', 'orchard']
    passphrase = f'{secrets.choice(adjectives)}_{secrets.choice(nouns)}_{secrets.randbelow(900) + 100}'

    def b64(value: str) -> str:
        return base64.b64encode(value.encode()).decode()

    # Index 0 holds btoa(btoa(passphrase)) — the check is btoa(input) === atob(arr[0]),
    # so unwrapping it twice in the console hands over the passphrase.
    strings = [
        b64(b64(passphrase)),   # 0 - expected btoa(passphrase)
        b64('denied'),          # 1
        b64('out'),             # 2
        b64('go'),              # 3
        b64('pw'),              # 4
        b64('ok'),              # 5
        b64('no'),              # 6
    ]

    key = passphrase
    payload = ', '.join(
        str(b ^ ord(key[i % len(key)])) for i, b in enumerate(ctx.flag.encode())
    )

    ident = secrets.token_hex(2)
    html = (_HTML
            .replace('__ID__', ident)
            .replace('__ARRAY__', ','.join(f"'{s}'" for s in strings))
            .replace('__PAYLOAD__', payload)
            .replace('__BUILD__', secrets.token_hex(3)))

    path = common.write(ctx.path('vault.html'), html)
    return {'description': DESCRIPTION, 'attachment': path}
