"""
Binary Exploitation 1 — Buffer Zone.

Teaching point: C will happily write past the end of an array, and what sits
past the end is whatever the compiler put next. No shellcode, no ROP, no
addresses — just one variable overwriting its neighbour, which is the mental
model everything harder is built on.
"""

from . import _common as common

SLUG        = 'buffer-zone'
TITLE       = 'Buffer Zone'
CATEGORY    = 'Binary Exploitation'
DIFFICULTY  = 'medium'
POINTS      = 200
DYNAMIC_FLAG = True

DESCRIPTION = """
<p>The gym's door terminal reads your name into a 32-byte field and then checks
your clearance level, which starts at zero and which you are definitely not
allowed to set.</p>

<p>Launch the instance and connect:</p>

<pre>nc HOST PORT</pre>

<p>(the exact host and port appear on this page once your instance is running)</p>

<p><em>Hints:</em></p>
<ul>
  <li>The terminal prints your clearance back to you after it reads your name.
      Feed it a short name, then a longer one, and watch the number.</li>
  <li>The name field holds 32 bytes. The clearance value lives immediately
      after it.</li>
  <li>Anything other than zero gets you in. You do not need a specific
      value.</li>
  <li>From the shell: <code>python3 -c "print('A'*40)" | nc HOST PORT</code></li>
</ul>
""".strip()


_SOURCE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct badge {
    char         name[32];
    unsigned int clearance;
    char         slack[64];   /* keeps a sloppy overflow inside our own frame */
};

static void print_flag(void)
{
    FILE *fh = fopen("flag.txt", "r");
    char buf[256];

    if (!fh) {
        puts("flag.txt is missing -- tell an organiser.");
        return;
    }
    if (fgets(buf, sizeof(buf), fh))
        printf("%s", buf);
    fclose(fh);
}

int main(void)
{
    struct badge b;

    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);

    memset(&b, 0, sizeof(b));

    puts("=====================================");
    puts("  CSIA GYM -- DOOR TERMINAL v0.3");
    puts("=====================================");
    puts("");
    puts("Name field: 32 bytes.");
    puts("Clearance : set by the system. Not by you.");
    puts("");
    printf("name> ");

    scanf("%s", b.name);          /* no bound. that is the bug. */

    printf("\nwelcome, %.32s\n", b.name);
    printf("clearance reads: %u\n", b.clearance);

    if (b.clearance != 0) {
        puts("");
        puts("[!] non-zero clearance accepted. door opening.");
        print_flag();
    } else {
        puts("");
        puts("[x] clearance zero. the door stays shut.");
    }
    return 0;
}
'''


def build(ctx):
    src = common.fresh_dir(ctx.path('src'))
    common.compile_c(_SOURCE, f'{src}/run')
    common.write(f'{src}/flag.txt', ctx.flag + '\n')
    archive = common.make_targz(src, ctx.path('buffer-zone.tar.gz'))
    return {'description': DESCRIPTION, 'nc_binary': archive}
