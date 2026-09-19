"""
challenges/_common.py
=====================
Stdlib-only helpers shared by the seeded challenge generators.

Everything in here has to run inside the platform container at boot, so it
deliberately avoids Pillow, exiftool, zip(1) and friends — struct, zlib,
tarfile and zipfile only.
"""

from __future__ import annotations

import base64
import os
import shutil
import struct
import subprocess
import tarfile
import zipfile
import zlib


# ── Filesystem ────────────────────────────────────────────────────────────────

def fresh_dir(path: str) -> str:
    """Remove `path` if it exists, recreate it empty, return it."""
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)
    return path


def write(path: str, data, mode: int | None = None) -> str:
    """Write bytes or str to `path`, creating parent dirs. Returns the path."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    if isinstance(data, str):
        data = data.encode()
    with open(path, 'wb') as fh:
        fh.write(data)
    if mode is not None:
        os.chmod(path, mode)
    return path


def make_targz(src_dir: str, out_path: str) -> str:
    """
    Tar-gzip the *contents* of src_dir (no wrapping top-level directory).

    The runner unwraps a single top-level dir anyway, but packing flat keeps
    the archive honest and makes the nc entrypoint search behave predictably.
    """
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    if os.path.exists(out_path):
        os.remove(out_path)
    with tarfile.open(out_path, 'w:gz') as tf:
        for name in sorted(os.listdir(src_dir)):
            tf.add(os.path.join(src_dir, name), arcname=name)
    return out_path


# ── C compilation ─────────────────────────────────────────────────────────────

class CompileError(RuntimeError):
    pass


def compile_c(source: str, out_path: str, extra_flags: list[str] | None = None) -> str:
    """
    Compile a C source string to an ELF at out_path.

    Stack protector and FORTIFY are switched off on purpose: these are teaching
    binaries whose whole point is that the bug is reachable.
    """
    src_path = out_path + '.c'
    write(src_path, source)
    flags = [
        'gcc', src_path, '-o', out_path,
        '-w',
        '-O0',
        '-fno-stack-protector',
        '-U_FORTIFY_SOURCE',
        '-D_FORTIFY_SOURCE=0',
    ]
    flags += extra_flags or []
    proc = subprocess.run(flags, capture_output=True, text=True)
    if proc.returncode != 0:
        raise CompileError(f'gcc failed for {out_path}:\n{proc.stderr}')
    os.remove(src_path)
    os.chmod(out_path, 0o755)
    return out_path


def c_byte_array(data: bytes, key: int) -> str:
    """Render `data` XORed with `key` as a C initialiser list."""
    return ', '.join(str(b ^ key) for b in data)


# ── PNG ───────────────────────────────────────────────────────────────────────

def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack('>I', len(payload)) + kind + payload
            + struct.pack('>I', zlib.crc32(kind + payload) & 0xFFFFFFFF))


def make_png(width: int, height: int, pixel_fn, text_chunks=None) -> bytes:
    """
    Build a truecolour PNG from scratch.

    pixel_fn(x, y) -> (r, g, b). text_chunks is a list of (keyword, value)
    rendered as tEXt chunks, which is what exiftool/strings surface as the
    image's metadata.
    """
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (None)
        for x in range(width):
            r, g, b = pixel_fn(x, y)
            raw += bytes((r & 0xFF, g & 0xFF, b & 0xFF))

    out = bytearray(b'\x89PNG\r\n\x1a\n')
    out += _png_chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    for keyword, value in (text_chunks or []):
        out += _png_chunk(b'tEXt', keyword.encode('latin-1') + b'\x00' + value.encode('latin-1'))
    out += _png_chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    out += _png_chunk(b'IEND', b'')
    return bytes(out)


# ── ZIP ───────────────────────────────────────────────────────────────────────

def make_zip(entries: dict[str, str | bytes], password_note: str | None = None) -> bytes:
    """Build a ZIP archive in memory from {arcname: content}."""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        if password_note:
            zf.comment = password_note.encode()
        for name, content in entries.items():
            if isinstance(content, str):
                content = content.encode()
            zf.writestr(name, content)
    return buf.getvalue()


# ── JPEG + EXIF ───────────────────────────────────────────────────────────────

_ASCII, _UNDEFINED, _LONG = 2, 7, 4


def _ifd_bytes(entries, ifd_offset, trailing=b'', next_ifd=0):
    """
    Serialise one little-endian TIFF IFD.

    entries: list of (tag, type, count, raw_bytes). Values of 4 bytes or fewer
    live inline; anything longer is appended to the data area and referenced by
    offset. `trailing` is extra data (e.g. a sub-IFD) placed after that area;
    callers that need to know where it lands can compute it with data_area_end.
    """
    n = len(entries)
    data_start = ifd_offset + 2 + 12 * n + 4
    table, data = bytearray(), bytearray()
    for tag, typ, count, raw in sorted(entries, key=lambda e: e[0]):
        if len(raw) <= 4:
            value = raw.ljust(4, b'\x00')
        else:
            value = struct.pack('<I', data_start + len(data))
            data += raw
            if len(data) % 2:
                data += b'\x00'
        table += struct.pack('<HHI', tag, typ, count) + value
    return (struct.pack('<H', n) + bytes(table) + struct.pack('<I', next_ifd)
            + bytes(data) + trailing)


def _ascii(value: str) -> bytes:
    return value.encode('latin-1', 'replace') + b'\x00'


def build_exif_app1(tags: dict[int, str], user_comment: str) -> bytes:
    """
    Build a complete APP1/Exif segment: TIFF header, IFD0 with the given ASCII
    tags, and an Exif SubIFD holding UserComment.
    """
    tiff_header = b'II' + struct.pack('<H', 42) + struct.pack('<I', 8)
    ifd0_offset = 8

    uc_payload = b'ASCII\x00\x00\x00' + user_comment.encode('latin-1', 'replace')
    sub_entries = [(0x9286, _UNDEFINED, len(uc_payload), uc_payload)]

    ascii_entries = [(tag, _ASCII, len(_ascii(v)), _ascii(v)) for tag, v in tags.items()]

    # Two passes: the first sizes IFD0 so we know where the SubIFD starts.
    probe = _ifd_bytes(ascii_entries + [(0x8769, _LONG, 1, struct.pack('<I', 0))], ifd0_offset)
    sub_offset = ifd0_offset + len(probe)
    sub_ifd = _ifd_bytes(sub_entries, sub_offset)

    ifd0 = _ifd_bytes(
        ascii_entries + [(0x8769, _LONG, 1, struct.pack('<I', sub_offset))],
        ifd0_offset,
        trailing=sub_ifd,
    )
    tiff = tiff_header + ifd0
    payload = b'Exif\x00\x00' + tiff
    return b'\xff\xe1' + struct.pack('>H', len(payload) + 2) + payload


def jpeg_with_exif(base_jpeg: bytes, tags: dict[int, str], user_comment: str) -> bytes:
    """
    Return base_jpeg with any existing APP1 replaced by a freshly built one.

    The segment is spliced in immediately after SOI so every EXIF reader —
    exiftool, the GNOME/Windows property panes, `strings` — finds it.
    """
    if not base_jpeg.startswith(b'\xff\xd8'):
        raise ValueError('base image is not a JPEG')

    # Drop pre-existing APP1 segments so we do not end up with two.
    out, i = bytearray(base_jpeg[:2]), 2
    while i < len(base_jpeg) - 1 and base_jpeg[i] == 0xFF:
        marker = base_jpeg[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xDA:  # start of scan — rest of the file is entropy-coded
            break
        seg_len = struct.unpack('>H', base_jpeg[i + 2:i + 4])[0]
        if marker != 0xE1:
            out += base_jpeg[i:i + 2 + seg_len]
        i += 2 + seg_len
    tail = base_jpeg[i:]

    return bytes(out[:2]) + build_exif_app1(tags, user_comment) + bytes(out[2:]) + tail


def load_asset(name: str) -> bytes:
    """Read a base64-encoded binary asset shipped next to this module."""
    path = os.path.join(os.path.dirname(__file__), 'assets', name)
    with open(path, 'rb') as fh:
        return base64.b64decode(fh.read())


# ── Text obfuscation used by the crypto challenges ────────────────────────────

def rot_n(text: str, n: int) -> str:
    out = []
    for ch in text:
        if 'a' <= ch <= 'z':
            out.append(chr((ord(ch) - 97 + n) % 26 + 97))
        elif 'A' <= ch <= 'Z':
            out.append(chr((ord(ch) - 65 + n) % 26 + 65))
        else:
            out.append(ch)
    return ''.join(out)


def xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
