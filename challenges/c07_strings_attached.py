"""
Reverse Engineering 1 — Strings Attached.

Teaching point: `strings` is the first tool you reach for and it is often
enough, but it only sees data that sits in the binary as plaintext. Anything
assembled at runtime is invisible to it — which is exactly why the password
falls out in seconds and the flag does not.
"""

import secrets

from . import _common as common

SLUG        = 'strings-attached'
TITLE       = 'Strings Attached'
CATEGORY    = 'Reverse Engineering'
DIFFICULTY  = 'easy'
POINTS      = 150
DYNAMIC_FLAG = False

DESCRIPTION = """
<p>A 64-bit Linux binary that wants a passphrase and will not tell you what it
is. The author thought encoding the passphrase counted as hiding it.</p>

<p>Download <code>gatekeeper</code>, make it executable, and talk your way
past it.</p>

<pre>chmod +x gatekeeper
./gatekeeper</pre>

<p><em>Hints:</em></p>
<ul>
  <li><code>strings gatekeeper</code> &mdash; then read what comes out and ask
      which of those lines does not look like a message meant for a human.</li>
  <li>Trailing <code>=</code> signs are a strong tell.</li>
  <li>The flag itself is <strong>not</strong> in the <code>strings</code>
      output. You have to get the passphrase right and let the binary build it
      for you.</li>
</ul>

<p>Built for <code>x86-64</code> Linux (Kali, Ubuntu, or WSL all work).</p>
""".strip()


_SOURCE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* passphrase, lightly "protected" */
static const char *vault = "__ENCODED__";

static const unsigned char blob[] = { __BLOB__ };
static const unsigned char mask = __MASK__;

static const char *b64 =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static int b64_decode(const char *in, unsigned char *out)
{
    int n = 0, val = 0, bits = -8;
    for (const char *p = in; *p; p++) {
        const char *hit = strchr(b64, *p);
        if (!hit) { if (*p == '=') break; else continue; }
        val = (val << 6) + (int)(hit - b64);
        bits += 6;
        if (bits >= 0) { out[n++] = (unsigned char)((val >> bits) & 0xFF); bits -= 8; }
    }
    out[n] = 0;
    return n;
}

static void unmask(const unsigned char *src, size_t len, unsigned char key, char *dst)
{
    for (size_t i = 0; i < len; i++)
        dst[i] = (char)(src[i] ^ key);
    dst[len] = 0;
}

int main(void)
{
    char attempt[128];
    unsigned char secret[128];
    char revealed[256];

    setvbuf(stdout, NULL, _IONBF, 0);

    b64_decode(vault, secret);

    puts("== GATEKEEPER ==");
    puts("The vault opens for those who know the word.");
    printf("passphrase> ");

    if (!fgets(attempt, sizeof(attempt), stdin)) {
        puts("\nnothing entered.");
        return 1;
    }
    attempt[strcspn(attempt, "\r\n")] = 0;

    if (strcmp(attempt, (const char *)secret) != 0) {
        puts("Wrong. The gate stays shut.");
        return 1;
    }

    unmask(blob, sizeof(blob), mask, revealed);
    puts("The gate swings open.");
    printf("%s\n", revealed);
    return 0;
}
'''


def build(ctx):
    import base64

    words = ['granite', 'lantern', 'harbour', 'cinder', 'marrow', 'thistle', 'quarry']
    passphrase = f'{secrets.choice(words)}-{secrets.choice(words)}-{secrets.randbelow(9000) + 1000}'
    encoded = base64.b64encode(passphrase.encode()).decode()

    mask = secrets.choice([b for b in range(0x11, 0xF0) if b not in (0x20, 0x7F)])
    blob = common.c_byte_array(ctx.flag.encode(), mask)

    source = (_SOURCE
              .replace('__ENCODED__', encoded)
              .replace('__BLOB__', blob)
              .replace('__MASK__', str(mask)))

    out = common.compile_c(source, ctx.path('gatekeeper'))
    return {'description': DESCRIPTION, 'attachment': out}
