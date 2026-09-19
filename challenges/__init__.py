"""
challenges
==========
The official CSIA GYM challenge set, built from source at first boot.

Nothing in this package stores a flag. Each module exposes metadata plus a
``build(ctx)`` function that receives the flag the seeder generated for that
challenge and returns the artifacts (and, where the flag is baked into the
prompt, the rendered description).

That split is deliberate: the repository is public, so the flags have to be
generated on the deployment rather than committed next to the sources.

Module contract
---------------
SLUG          str   stable identifier, also the artifact directory name
TITLE         str   shown on the challenge list
CATEGORY      str   must match the platform's category strings exactly
DIFFICULTY    str   'easy' | 'medium' | 'hard'
POINTS        int
DYNAMIC_FLAG  bool  True when the archive ships a flag.txt and the runner
                    should mint a fresh per-player flag on every launch
build(ctx)    ->    dict with 'description' and at most one of
                    'web_archive' | 'nc_binary' | 'misc_file' | 'attachment'
                    (optionally 'flag', 'is_regex')
"""

import os

from . import (
    c01_cookie_monster,
    c02_blind_trust,
    c03_rotten_base,
    c04_one_byte_wonder,
    c05_say_cheese,
    c06_zipped_lips,
    c07_strings_attached,
    c08_minified_mayhem,
    c09_buffer_zone,
    c10_out_of_bounds,
)

#: Seeding order — also the order they appear on a freshly built scoreboard.
MODULES = [
    c01_cookie_monster,
    c02_blind_trust,
    c03_rotten_base,
    c04_one_byte_wonder,
    c05_say_cheese,
    c06_zipped_lips,
    c07_strings_attached,
    c08_minified_mayhem,
    c09_buffer_zone,
    c10_out_of_bounds,
]


class BuildContext:
    """Everything a challenge module needs in order to produce its artifacts."""

    def __init__(self, flag: str, out_dir: str):
        self.flag = flag
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)

    def path(self, *parts: str) -> str:
        return os.path.join(self.out_dir, *parts)


def spec_of(module) -> dict:
    return {
        'slug': module.SLUG,
        'title': module.TITLE,
        'category': module.CATEGORY,
        'difficulty': module.DIFFICULTY,
        'points': module.POINTS,
        'dynamic_flag': module.DYNAMIC_FLAG,
        'module': module,
    }


def all_specs() -> list[dict]:
    return [spec_of(m) for m in MODULES]
