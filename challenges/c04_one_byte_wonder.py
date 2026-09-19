"""
Cryptography 2 — One Byte Wonder.

Teaching point: a one-byte key has 256 possible values, so "brute force" is a
loop you can write in four lines. Key length is what buys you security, and a
single byte buys you none.
"""

import secrets

from . import _common as common

SLUG        = 'one-byte-wonder'
TITLE       = 'One Byte Wonder'
CATEGORY    = 'Cryptography'
DIFFICULTY  = 'easy'
POINTS      = 150
DYNAMIC_FLAG = False

_TEMPLATE = """
<p>A first-year swore they had written "military grade encryption" for their
class project. This is the ciphertext, in hex:</p>

<pre>{payload}</pre>

<p>It is XOR. The key is one byte long.</p>

<p><em>Hint:</em> one byte means 256 possibilities, so you do not need to be
clever &mdash; you need to be quick. CyberChef has an <strong>XOR Brute
Force</strong> operation, and a Python loop over <code>range(256)</code> does
the same job. You know the plaintext contains <code>CSIA{{</code>, so you know
exactly what a correct guess looks like.</p>
""".strip()


def build(ctx):
    message = f'the flag is {ctx.flag} and one byte was never going to be enough'
    key = secrets.choice([b for b in range(1, 256) if b not in (0x20, 0x0A, 0x0D)])
    payload = common.xor_bytes(message.encode(), bytes([key])).hex()
    return {'description': _TEMPLATE.format(payload=payload)}
