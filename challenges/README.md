# Official challenge set

The ten challenges that CSIA GYM publishes on first boot. Two per category:
Web Exploitation, Cryptography, Forensics, Reverse Engineering, and Binary
Exploitation.

| # | Category | Title | Difficulty | Points | Delivery |
|---|---|---|---|---|---|
| 1 | Web Exploitation | Cookie Monster | easy | 100 | Docker instance |
| 2 | Web Exploitation | Blind Trust | easy | 150 | Docker instance |
| 3 | Cryptography | Rotten Base | easy | 100 | ciphertext in the prompt |
| 4 | Cryptography | One Byte Wonder | easy | 150 | ciphertext in the prompt |
| 5 | Forensics | Say Cheese | easy | 100 | `badge_photo.jpg` |
| 6 | Forensics | Zipped Lips | easy | 150 | `schedule.png` |
| 7 | Reverse Engineering | Strings Attached | easy | 150 | `gatekeeper` (x86-64 ELF) |
| 8 | Reverse Engineering | Minified Mayhem | easy | 150 | `vault.html` |
| 9 | Binary Exploitation | Buffer Zone | medium | 200 | Docker instance (`nc`) |
| 10 | Binary Exploitation | Out of Bounds | medium | 250 | Docker instance (`nc`) |

Total: 1500 points.

## No flags live in this repository

This repository is public, so nothing here stores a flag. Each module exposes
metadata plus a `build(ctx)` function; `ctx.flag` is generated on the
deployment at first boot and the module bakes it into whatever artifact it
produces. Flags for the non-launchable challenges are recorded in
`instance/seed_flags.json` (mode 0600, and `instance/` is gitignored).

The four Docker-backed challenges ship a `flag.txt`, so the runner overwrites
it with a fresh per-player flag on every launch. Those flags are unguessable
and worthless to anyone but the player who earned them.

## Pinning a flag

To fix a flag before an event — useful if you want to print the answer key in
advance — set an environment variable before first boot:

```bash
SEED_FLAG_ROTTEN_BASE='CSIA{your_value_here}'
```

The variable name is the slug, upper-cased, with hyphens turned into
underscores. Precedence is env var → `instance/seed_flags.json` → freshly
minted.

## Reading the answer key

```bash
python3 scripts/show_seed_flags.py
```

## Resetting one challenge

Delete it in `/admin/challenges` and restart the platform. The seeder notices
it is missing, rebuilds it, and reuses the flag already recorded in the store
so any writeup you prepared stays accurate.

## Turning seeding off

```bash
SEED_CHALLENGES=0
```

## Adding your own

Drop a module in this package following the contract documented in
`__init__.py`, then add it to `MODULES`. Artifacts are built at seed time from
source, so the build helpers in `_common.py` are stdlib-only — they have to run
inside the platform container, which has `gcc` and Python 3.11 and not much
else.

## Build requirements

- `gcc` (challenges 9, 10 and 7 compile at seed time) — already in the
  platform `Dockerfile`
- Python 3.11 standard library — no Pillow, no exiftool, no `zip(1)`

## Verifying a deployment

Start the platform and read the startup log — the seeder logs one `seed:` line
per challenge it publishes, and logs the build traceback (without failing the
boot) for any challenge it could not build.

The build-and-solve harness used during development is deliberately **not** in
this repository: it contains a working exploit for all ten challenges, and this
repository is public.
