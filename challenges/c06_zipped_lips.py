"""
Forensics 2 — Zipped Lips.

Teaching point: file type is decided by the bytes, not the extension, and most
formats do not care what is glued on after the part they need. One file can be
honestly a PNG and honestly a ZIP at the same time.
"""

from . import _common as common

SLUG        = 'zipped-lips'
TITLE       = 'Zipped Lips'
CATEGORY    = 'Forensics'
DIFFICULTY  = 'easy'
POINTS      = 150
DYNAMIC_FLAG = False

DESCRIPTION = """
<p><code>schedule.png</code> opens fine in any image viewer. It is a picture of
nothing in particular, and it is 40 KB larger than a picture of nothing in
particular has any business being.</p>

<p>Something is riding along behind the image.</p>

<p><em>Hints:</em></p>
<ul>
  <li><code>file schedule.png</code> will confidently tell you it is a PNG. It
      is only reading the first few bytes.</li>
  <li><code>binwalk schedule.png</code> lists <em>every</em> file signature it
      finds, not just the one at offset 0.</li>
  <li>If binwalk is not installed, try <code>unzip schedule.png</code> anyway
      and see what happens.</li>
</ul>
""".strip()


_README = """CSIA GYM — internal
====================

If you are reading this you either ran binwalk or you got lucky with unzip.
Either way: appending an archive to an image is one of the oldest tricks in
the book, and it still works because PNG readers stop at IEND and ZIP readers
start from the end of the file.

Files in here:
  roster.csv   - not the flag
  notes.txt    - not the flag
  vault/       - warmer
"""

_ROSTER = """id,handle,category,solved
1,r3dqu33n,web,4
2,nullptr,pwn,7
3,mothman,forensics,5
4,sseccatoor,organiser,0
"""

_NOTES = """reminders
- book the room for the bootcamp
- the projector HDMI cable is cursed, bring the adapter
- stop hiding things in image files (nobody will do this)
"""


def _pixel(x, y):
    # Diagonal red-on-black banding with a lighter frame, so the PNG is a
    # real (if dull) picture rather than a flat colour block.
    if x < 6 or y < 6 or x > 593 or y > 393:
        return (120, 18, 26)
    band = ((x + y) // 18) % 3
    if band == 0:
        return (18, 14, 18)
    if band == 1:
        return (34, 12, 18)
    return (58, 16, 24)


def build(ctx):
    png = common.make_png(600, 400, _pixel, text_chunks=[
        ('Title', 'CSIA GYM bootcamp schedule'),
        ('Software', 'csia-export 2.1.4'),
        ('Comment', 'nothing to see in the metadata this time'),
    ])
    payload = common.make_zip({
        'README.txt': _README,
        'roster.csv': _ROSTER,
        'notes.txt': _NOTES,
        'vault/flag.txt': ctx.flag + '\n',
    })
    path = common.write(ctx.path('schedule.png'), png + payload)
    return {'description': DESCRIPTION, 'attachment': path}
