"""
Cryptography 1 — Rotten Base.

Teaching point: encoding is not encryption. Base64 and ROT13 are both
reversible with no key at all, and real-world "obfuscation" is very often just
two or three of these stacked. Recognising the shape of an encoding is the
whole skill.
"""

import base64

from . import _common as common

SLUG        = 'rotten-base'
TITLE       = 'Rotten Base'
CATEGORY    = 'Cryptography'
DIFFICULTY  = 'easy'
POINTS      = 100
DYNAMIC_FLAG = False

_TEMPLATE = """
<p>Someone pasted this into the society group chat at 2am with the message
"lol decode it". Nobody did. Be the person who does.</p>

<pre>{payload}</pre>

<p>Two layers. Neither of them is encryption.</p>

<p><em>Hint:</em> the character set and the <code>=</code> padding at the end
tell you what the outer layer is. What comes out of it will look like English
that has been sitting in the sun too long.</p>
""".strip()


def build(ctx):
    message = (f'Nicely spotted. The flag for this challenge is {ctx.flag} '
               f'and the lesson is that encoding is not encryption.')
    payload = base64.b64encode(common.rot_n(message, 13).encode()).decode()
    return {'description': _TEMPLATE.format(payload=payload)}
