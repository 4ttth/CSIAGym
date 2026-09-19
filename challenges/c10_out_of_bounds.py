"""
Binary Exploitation 2 — Out of Bounds.

Teaching point: a bounds check that only checks one end is not a bounds check.
The index is read as a signed integer, the upper limit is enforced, the lower
limit is assumed — and the thing sitting just before the array is the thing
you were not supposed to read.
"""

from . import _common as common

SLUG        = 'out-of-bounds'
TITLE       = 'Out of Bounds'
CATEGORY    = 'Binary Exploitation'
DIFFICULTY  = 'medium'
POINTS      = 250
DYNAMIC_FLAG = True

DESCRIPTION = """
<p>Ten lockers, numbered 0 through 9. The attendant checks that you have not
asked for a locker above 9. The attendant is very proud of this check.</p>

<p>Launch the instance and connect:</p>

<pre>nc HOST PORT</pre>

<p><em>Hints:</em></p>
<ul>
  <li>Read the validation message carefully. It tells you exactly which half of
      the range it is guarding.</li>
  <li>The locker number is read with <code>%d</code>. What kinds of number can
      <code>%d</code> accept?</li>
  <li>Memory before an array is still memory.</li>
</ul>

<p>No debugger needed. This is one keystroke, once you see it.</p>
""".strip()


_SOURCE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Layout is load-bearing: `stash` sits immediately before `locker`,
   so locker[-1] is stash. */
struct vault {
    char *stash;
    char *locker[10];
};

static char flagbuf[256];

static void load_flag(void)
{
    FILE *fh = fopen("flag.txt", "r");

    if (!fh) {
        snprintf(flagbuf, sizeof(flagbuf), "flag.txt is missing -- tell an organiser.");
        return;
    }
    if (!fgets(flagbuf, sizeof(flagbuf), fh))
        snprintf(flagbuf, sizeof(flagbuf), "flag.txt is empty -- tell an organiser.");
    flagbuf[strcspn(flagbuf, "\r\n")] = 0;
    fclose(fh);
}

int main(void)
{
    struct vault v;
    int idx;
    static const char *contents[10] = {
        "a single unpaired glove",
        "protein powder, expired 2019",
        "someone's dissertation, printed",
        "a padlock with no key",
        "three HDMI adapters, all the wrong shape",
        "a towel that has seen things",
        "an unopened energy drink",
        "gym shoes. do not open.",
        "a USB stick labelled 'DO NOT PLUG IN'",
        "nothing at all"
    };

    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);

    load_flag();
    v.stash = flagbuf;
    for (int i = 0; i < 10; i++)
        v.locker[i] = (char *)contents[i];

    puts("=====================================");
    puts("  CSIA GYM -- LOCKER ATTENDANT");
    puts("=====================================");
    puts("");
    puts("Lockers 0 to 9 are available to members.");
    puts("Anything above 9 is not a locker and I will not look it up.");
    puts("");
    printf("locker number> ");

    if (scanf("%d", &idx) != 1) {
        puts("that was not a number.");
        return 1;
    }

    if (idx > 9) {                 /* upper bound only. that is the bug. */
        puts("");
        printf("[x] locker %d is above the maximum of 9. request refused.\n", idx);
        return 1;
    }

    puts("");
    printf("[*] opening locker %d ...\n", idx);
    printf("    contents: %s\n", v.locker[idx]);
    return 0;
}
'''


def build(ctx):
    src = common.fresh_dir(ctx.path('src'))
    common.compile_c(_SOURCE, f'{src}/run')
    common.write(f'{src}/flag.txt', ctx.flag + '\n')
    archive = common.make_targz(src, ctx.path('out-of-bounds.tar.gz'))
    return {'description': DESCRIPTION, 'nc_binary': archive}
