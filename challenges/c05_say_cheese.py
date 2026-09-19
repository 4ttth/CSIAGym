"""
Forensics 1 — Say Cheese.

Teaching point: a photograph is a container, not just pixels. EXIF carries the
camera, the software, the author and whatever free-text the export pipeline
felt like writing, and almost nobody strips it before publishing.
"""

from . import _common as common

SLUG        = 'say-cheese'
TITLE       = 'Say Cheese'
CATEGORY    = 'Forensics'
DIFFICULTY  = 'easy'
POINTS      = 100
DYNAMIC_FLAG = False

DESCRIPTION = """
<p>This is the only surviving photo from the last bootcamp. It is a bad photo.
The photographer's export tool was chattier than the photographer.</p>

<p>Download <code>badge_photo.jpg</code> and find what the file is saying about
itself.</p>

<p><em>Hint:</em> on Kali, <code>exiftool badge_photo.jpg</code>. No terminal?
<code>strings</code> in the browser is not a thing, but
<a href="https://exif.tools/" target="_blank" rel="noopener">exif.tools</a> and
similar online EXIF viewers will read the same fields. Look past the obvious
ones.</p>
""".strip()


def build(ctx):
    base = common.load_asset('badge_photo.jpg.b64')
    tags = {
        0x010E: 'CSIA GYM bootcamp - cohort badge photo (do not distribute)',
        0x010F: 'CSIA',
        0x0110: 'GYM-CAM mk1',
        0x0131: 'csia-export 2.1.4',
        0x013B: 'sseccatoor',
        0x8298: 'Copyright 2026 HAU CSIA. All rights reserved.',
    }
    comment = (f'export note: verification string {ctx.flag} '
               f'-- strip this before publishing, seriously')
    data = common.jpeg_with_exif(base, tags, comment)
    path = common.write(ctx.path('badge_photo.jpg'), data)
    return {'description': DESCRIPTION, 'attachment': path}
