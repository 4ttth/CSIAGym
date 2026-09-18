<div align="center">

# CSIA GYM

**Train. Hack. Dominate.**

A self-hosted Capture-The-Flag platform with per-player isolated challenge
containers, a ranked progression system, passkey authentication, and a
community wall — built with Flask, Docker, and a deliberately brutalist
red-on-black interface.

[![License: MIT](https://img.shields.io/badge/License-MIT-8b0000.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-1a1a1a.svg)](https://www.python.org/)
[![Flask 3.0](https://img.shields.io/badge/flask-3.0-1a1a1a.svg)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/docker-compose-1a1a1a.svg)](https://docs.docker.com/compose/)

</div>

---

## Table of contents

- [What is this project?](#what-is-this-project)
- [Feature tour](#feature-tour)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Quick start (Docker, recommended)](#quick-start-docker-recommended)
  - [Local development without Docker](#local-development-without-docker)
  - [Production deployment](#production-deployment)
- [Configuration reference](#configuration-reference)
- [Challenge authoring](#challenge-authoring)
- [Ranks, XP, and badges](#ranks-xp-and-badges)
- [Easter eggs](#easter-eggs)
- [Operations](#operations)
- [Security posture](#security-posture)
- [Documentation map](#documentation-map)
- [Contributing](#contributing)
- [License](#license)

---

## What is this project?

CSIA GYM is a **Capture The Flag (CTF) training platform** — a website where
people learn offensive security by solving hands-on hacking challenges.

A CTF challenge is a deliberately vulnerable artifact: a web app with a SQL
injection, an encrypted file, a stripped binary with a buffer overflow, a packet
capture hiding a password. Somewhere inside each one is a **flag** — a string in
the form `CSIA{...}` — that proves you solved it. You paste the flag into the
site, you get points, you move up the scoreboard.

What separates this from a static list of downloads is that CSIA GYM **runs the
challenges for you**. Press *Launch* on a Web or Binary Exploitation challenge
and a sidecar service spins up a Docker container that belongs to you alone, on
your own port, with your own flag baked into it, for fifteen minutes. Your
exploitation cannot disturb anyone else's, and the flag you extract is
worthless to anybody but you.

It was built as a training gym for a university cybersecurity society (the
project's domain, `haucsia.com`, and the `CSIA{}` flag prefix both come from
there), and it is designed for a cohort of roughly 100 concurrent players on a
single modest VPS.

### Who it is for

| You are | CSIA GYM gives you |
|---|---|
| **A player** | A catalogue of challenges, a private container per attempt, per-user flags, a percentile-ranked scoreboard, first-blood tracking, badges, bookmarks, and a community wall for writeups and hints. |
| **A challenge author** | A submission form that accepts a description, a flag (literal or regex), and an artifact — a `.tar.gz` web app, a Linux ELF binary, or any file — which an admin reviews before it goes live. |
| **An administrator** | A full web console: user management, bans and timeouts, challenge approval, content moderation, badge and milestone design, timed announcements, a CSV audit log, and passkey-gated confirmation on destructive actions. |
| **A club or course** | A single `docker compose up` deployment that owns its own data, with no external CTF service, no per-seat pricing, and an MIT licence. |

### What makes it distinctive

- **Per-user challenge instances.** Every player gets their own container, port, and filesystem. No shared state, no griefing.
- **Per-user dynamic flags.** For challenges containing a `flag.txt`, the runner generates a fresh `CSIA{sha256...}` per player and injects it at launch. Sharing a flag with a friend does not help them.
- **Instances self-destruct.** 15-minute TTL, extendable to a 60-minute hard cap, reaped every 30 seconds, and killed immediately the moment you submit the correct flag.
- **Passkeys, not just passwords.** WebAuthn registration and login, plus a "passkey sudo" re-authentication gate in front of dangerous admin actions.
- **A ranking system with teeth.** Ten percentile tiers from *Neo Initiate* to *Master of the Nexus*, plus five Legendary tiers that sit outside the percentile system entirely — one of which is granted by an admin, one of which can only be *found*, and one of which nobody can obtain at all. See [Easter eggs](#easter-eggs).

---

## Feature tour

<details open>
<summary><strong>Challenges</strong></summary>

- Nine categories: Web Exploitation, Cryptography, Binary Exploitation (PWN), Reverse Engineering, Forensics, OSINT, Steganography, Networking, Miscellaneous.
- Three difficulties (`easy` / `medium` / `hard`) with weights `1.0` / `2.2` / `4.5` feeding the ranking engine.
- Filter by category, difficulty, source (Official vs Community), and free-text search across title and description.
- **Launchable instances** for Web, Binary Exploitation, and Misc challenges — start, stop, extend, and live status polling.
- **Literal or regex flags.** Authors can mark a flag as a regular expression matched with `re.fullmatch`.
- **Dynamic per-user flags** for any challenge whose archive contains a `flag.txt`.
- **First blood** — the first three solvers of each challenge are recorded and shown a medal position.
- Bookmarks (save for later) and subscriptions (get notified when somebody solves a challenge you follow).
- Per-challenge community upvote/downvote.
- File attachments per challenge, served through an authenticated, path-traversal-checked download route.

</details>

<details open>
<summary><strong>Players and progression</strong></summary>

- Registration with an auto-generated deterministic **identicon** avatar (SHA-256 of the username → a symmetric 5×5 grid), replaceable with a croppable upload.
- Profiles: full name, affiliation, age, gender, bio, and links for GitHub, LinkedIn, Facebook, Discord, and a contact number.
- Public profiles at `/user/<id>`, with a **radar chart** comparing your per-category strength against up to four other players.
- Percentile **ranks** with animated CSS treatments that escalate with tier (see [Ranks, XP, and badges](#ranks-xp-and-badges)).
- **Badges** with ten border tiers, optional limited-edition counts (`#3/50`), event-only and unattainable flags, seven automatic award rules, and secret claim links.
- **Milestones** — a honeycomb of achievement tiles on your profile.
- A public **scoreboard**, which admins can hide individual accounts from.

</details>

<details open>
<summary><strong>Community</strong></summary>

- A post wall with rich text (Quill), flairs (*Challenge Discussion*, *Writeups*, *For Beginners*, *Need Help*, *Tutorial*), image uploads auto-converted to WebP, upvotes, and sorting.
- Threaded comments with six emoji reactions and spoiler formatting for writeups.
- Moderation: pin, archive, disable comments, disable reactions, edit, delete — available to admins, moderators, and the original poster as appropriate.
- **Private mail** between users, with an inbox/sent split and unread counts in the navbar.
- **Notifications** — global admin broadcasts and per-user targeted notifications, each individually opt-out-able in settings.
- **Announcements** — timed site-wide banners with a start and end time.
- **Bug reports** from any page, triaged by admins with a severity and status.

</details>

<details open>
<summary><strong>Administration</strong></summary>

- Dashboard with live counts, plus dedicated pages for users, challenges, posts, badges, badge rules, milestones, notifications, announcements, bug reports, flag submissions, and statistics.
- User actions: promote/demote admin, grant/revoke moderator, ban with a reason, temporary timeout, hide from scoreboard, regenerate avatar, edit profile, assign badges, delete.
- Challenge review queue: approve, reject, edit, toggle visibility, mark unofficial, delete, and manually credit a solve to a named user.
- **Passkey sudo** — sensitive actions require a fresh WebAuthn assertion within the last 60 seconds.
- **CSV audit log** covering five categories (`admin`, `auth`, `challenge`, `community`, `submission`) with client IP, downloadable from the console.

</details>

<details open>
<summary><strong>Interface</strong></summary>

- Brutalist design language: black canvas, `#8b0000` blood-red accents, sharp edges, heavy uppercase type, animated particle background.
- A **guided spotlight tour** — nine per-page scripted walkthroughs (`app/static/js/tour-*.js`) that run once and remember dismissal.
- A `/whats-new` changelog rendered straight from [`WHATS-NEW.md`](WHATS-NEW.md); the app parses the version out of its first line and shows it in the footer.
- Custom-designed 400/403/404/405/500 error pages.
- Mobile support for a deliberately restricted subset of pages — see [Mobile access](#mobile-access).

</details>

---

## Architecture

Three containers, one job each. The split exists for one reason: **challenge
code is hostile code**, and the process that starts it should not be the process
that holds your user table.

```
                    ┌──────────────────────────────────────────┐
   players ────────▶│  nginx        :80 / :443                 │
                    │  TLS termination, reverse proxy          │
                    └────────────────────┬─────────────────────┘
                                         │
                    ┌────────────────────▼─────────────────────┐
                    │  web          :5050   (gunicorn)         │
                    │  ── Flask application ──                 │
                    │   8 blueprints · SQLAlchemy · Flask-Login │
                    │   CSRFProtect · WebAuthn · bleach         │
                    │                                          │
                    │   SQLite  →  /app/instance/ctf.db        │
                    └────────────────────┬─────────────────────┘
                                         │  HTTP + X-Runner-Secret
                                         │  (bound to 127.0.0.1 only)
                    ┌────────────────────▼─────────────────────┐
                    │  runner       :32526  (FastAPI/uvicorn)  │
                    │  owns /var/run/docker.sock               │
                    └────────────────────┬─────────────────────┘
                                         │  docker run
              ┌──────────────────────────┼──────────────────────────┐
              ▼                          ▼                          ▼
    ┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
    │ chal_web_7_u12    │    │ chal_nc_3_u12     │    │ chal_misc_9_u40   │
    │ php / node / java │    │ socat → ELF       │    │ static / detected │
    │ python / static   │    │                   │    │                   │
    │ 128 MB · 0.25 CPU │    │ 128 MB · 0.25 CPU │    │ 128 MB · 0.25 CPU │
    │ 64 pids · 15 min  │    │ 64 pids · 15 min  │    │ 64 pids · 15 min  │
    │ port 10000-11999  │    │ port 10000-11999  │    │ port 10000-11999  │
    └───────────────────┘    └───────────────────┘    └───────────────────┘
```

### The web tier

A standard Flask application factory (`app/__init__.py` → `create_app()`), with
eight blueprints:

| Blueprint | Module | Responsibility |
|---|---|---|
| `auth` | `app/routes/auth.py` | Register, login, logout, landing page, changelog |
| `challenges` | `app/routes/challenges.py` | Listing, detail, flag submission, instance lifecycle, scoreboard, bookmarks, badge claims |
| `submissions` | `app/routes/submissions.py` | Player-authored challenge submissions and file quota |
| `community` | `app/routes/community.py` | Posts, comments, reactions, upvotes, image upload |
| `settings` | `app/routes/settings.py` | Profile, avatars, notification preferences, ranks, badges, bug reports |
| `admin` | `app/routes/admin.py` | The entire admin console (`/admin/*`) |
| `passkey` | `app/routes/passkey.py` | WebAuthn registration, authentication, and sudo |
| `mail` | `app/routes/mail.py` | User-to-user private messages |

Supporting modules:

| Module | Purpose |
|---|---|
| `app/models.py` | ~30 SQLAlchemy models |
| `app/ranking.py` | Percentile engine, rank/legendary tier definitions, CSS treatments, automatic badge rules |
| `app/challenge_runner.py` | Thin HTTP client for the runner sidecar |
| `app/notifs.py` | Notification fan-out (solves, subscribers, first blood) |
| `app/identicon.py` | Deterministic avatar generation |
| `app/image_utils.py` | Avatar encoding to 500×500 WebP |

### Schema management

There is **no migration framework**. `create_app()` runs `db.create_all()` and
then a long sequence of idempotent `CREATE TABLE IF NOT EXISTS` and
`PRAGMA table_info` / `ALTER TABLE ADD COLUMN` statements — roughly 500 lines of
hand-rolled forward-only migration that executes on every boot. This works, and
it is the single largest piece of technical debt in the codebase. See
[`audit-docs/development-audit.md`](audit-docs/development-audit.md).

### The runner sidecar

`runner/main.py` is a FastAPI service that holds the Docker socket and exposes
`/launch`, `/stop`, `/extend`, and `/status`, authenticated by a shared
`RUNNER_SECRET` compared with `secrets.compare_digest`. It is published on
`127.0.0.1:32526` only — never expose it.

On launch it extracts the author's archive into a per-user working directory,
rewrites every `flag.txt` it finds with a freshly generated flag, sniffs the
runtime, and starts a container:

| Detected | Image | Command |
|---|---|---|
| any `*.php` | `php:8.2-cli-alpine` | `php -S 0.0.0.0:{port} -t /app` |
| `package.json` with a `start` script | `node:20-alpine` | `npm install && npm start` |
| `index.js` / `server.js` / `app.js` | `node:20-alpine` | `node <file>` |
| `index.ts` / `server.ts` / `app.ts` | `node:20-alpine` | `npx ts-node <file>` |
| any `*.jar` | `eclipse-temurin:21-jre-alpine` | `java -jar` |
| `app.py` / `main.py` / `server.py` | `python:3.11-alpine` | `pip install -r requirements.txt; python <file>` |
| nothing recognised | `python:3.11-alpine` | `python -m http.server` |
| Binary Exploitation | `ctf-nc-base` (Debian + socat) | `socat TCP-LISTEN:{port},fork EXEC:/app/.run.sh` |

A background reaper thread sweeps every 30 seconds for expired or dead
instances and removes both the container and its working directory.

> [!WARNING]
> Instance state lives in a Python dict in the runner process. Restarting the
> runner orphans every live container. Tracked in
> [`audit-docs/development-audit.md`](audit-docs/development-audit.md).

---

## Repository layout

```
.
├── README.md                    ← you are here
├── LICENSE                      MIT
├── WHATS-NEW.md                 changelog — READ AT RUNTIME, must stay at root
│
├── run.py                       WSGI entry point (`app` object for gunicorn)
├── config.py                    Config class, fails fast without SECRET_KEY
├── requirements.txt             pinned Python dependencies
│
├── Dockerfile                   web tier image (Python 3.11 + nsjail + runtimes)
├── docker-compose.yml           default stack: web + runner + nginx
├── docker-compose.dev.yml       opt-in dev overlay (bind mount, FLASK_ENV=development)
├── docker-compose.prod.yml      slim production overlay with memory limits
├── .env.template                copy to .env, then run scripts/generate_secrets.py
│
├── app/                         the Flask application package
│   ├── __init__.py              create_app(), context processors, schema bootstrap
│   ├── models.py                ~30 SQLAlchemy models
│   ├── ranking.py               percentile engine, rank tiers, badge rules
│   ├── challenge_runner.py      HTTP client for the runner sidecar
│   ├── notifs.py                notification fan-out
│   ├── identicon.py             deterministic avatar generation
│   ├── image_utils.py           WebP avatar encoding
│   ├── routes/                  8 blueprints
│   ├── templates/               Jinja2 templates, grouped by feature
│   └── static/                  CSS, JS (incl. 9 page tours), images, seed avatars
│
├── runner/                      challenge-execution sidecar (separate image)
│   ├── main.py                  FastAPI service, owns the Docker socket
│   ├── Dockerfile
│   └── requirements.txt
│
├── scripts/
│   └── generate_secrets.py      one-shot .env secret generator
│
├── deploy/
│   ├── nginx/nginx.conf.template    fill in and save as nginx.conf (git-ignored)
│   ├── cloudflare/worker.js         idle-instance redirect for *.chal.<domain>
│   └── ssl/README.md                where to drop certificates (contents ignored)
│
├── docs/
│   ├── customization.md         add features, change branding
│   ├── database-and-admin.md    admin features, scaling, backups
│   ├── file-attachments.md      challenge file handling
│   ├── troubleshooting.md       error → fix
│   └── roadmap.md               outstanding work, verbatim from the authors
│
├── audit-docs/                  ← development audit, security audit, fix plan
│   ├── README.md
│   ├── development-audit.md
│   ├── security-audit.md
│   └── remediation-plan.md
│
└── archive/                     retained for provenance, not shipped
    ├── legacy-runners/          superseded subprocess-based runners
    └── q-dev-chat-*.md          development transcripts
```

> [!NOTE]
> **Two paths are load-bearing and must not move.** `WHATS-NEW.md` is read at
> import time by `app/__init__.py` and at request time by `app/routes/auth.py`;
> `instance/` is resolved relative to the package as `app/../../instance` by
> every upload, avatar, badge, and challenge-file route.

---

## Setup

### Prerequisites

| Requirement | Notes |
|---|---|
| **Docker Engine 20.10+** and the Compose V2 plugin | `docker compose version` must work. Docker Desktop is fine on macOS/Windows. |
| **~2 GB RAM** | The `web` container plus a handful of 128 MB challenge instances. |
| **~5 GB disk** | The web image is large — it builds nsjail and ships PHP, Node, and a JRE. |
| **Ports 5050, 80, 443, 10000–11999** | Challenge instances bind host ports directly. |
| **Python 3.11** | Only for running without Docker. |

### Quick start (Docker, recommended)

```bash
# 1. Clone
git clone https://github.com/4ttth/CSIAGym.git
cd CSIAGym

# 2. Create .env and fill in the two generated secrets
cp .env.template .env
python3 scripts/generate_secrets.py

# 3. Tell the stack where instance data should live on the HOST
#    (this path is bind-mounted into both containers)
mkdir -p /opt/ctf/instance
echo 'HOST_INSTANCE_DIR=/opt/ctf/instance' >> .env

# 4. Render the nginx config from its template
cp deploy/nginx/nginx.conf.template deploy/nginx/nginx.conf
${EDITOR:-nano} deploy/nginx/nginx.conf     # replace __SERVER_NAME__, __SSL_CERT__, __SSL_KEY__

# 5. Build and start
docker compose up --build
```

The stack is then reachable at **<http://localhost:5050>** (direct) or through
nginx on ports 80/443.

#### Step 6 — retrieve the admin password

On first boot the app creates an `admin` account with a random
`secrets.token_urlsafe(16)` password and prints a banner to **stderr**:

```
============================================================
✅ Admin account created!
   Username: admin  |  Password: [see application startup log]
   Password hint: cY5m******************
   ⚠️  Change this password after first login!
============================================================
```

> [!CAUTION]
> **The banner never prints the password.** It prints the first four characters
> and masks the rest, so a fresh deployment currently has **no way to log in as
> `admin`**. This is a confirmed blocking defect
> ([DEV-01](audit-docs/development-audit.md)) with a one-line fix.
>
> Until it is patched, set the password by hand after the first boot:
>
> ```bash
> docker compose exec web python -c "
> from app import create_app, db
> from app.models import User
> app = create_app()
> with app.app_context():
>     u = User.query.filter_by(username='admin').first()
>     u.set_password('<a-strong-password-you-choose>')
>     db.session.commit()
>     print('admin password set')
> "
> ```

Log in at `/login`, then immediately:

1. Change the admin password at `/settings`.
2. Register a passkey — admin destructive actions are gated behind passkey sudo.
3. Create your first challenge from `/admin/challenges`.

### Local development without Docker

Useful for editing templates and routes. Note that **challenge launching will
not work** — that needs the runner sidecar and a Docker socket.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export DATABASE_URL="sqlite:///$(pwd)/instance/ctf.db"
export FLASK_ENV=development          # relaxes Secure-cookie enforcement over http://
mkdir -p instance

python run.py                          # serves on http://127.0.0.1:5000
```

`config.py` raises at import time if `SECRET_KEY` is unset — that is
intentional, and it is the correct behaviour. Do not work around it by
hard-coding a key.

`FLASK_ENV=development` turns off `SESSION_COOKIE_SECURE` and
`REMEMBER_COOKIE_SECURE` so cookies survive plain HTTP on localhost. **Never set
it in production**; over HTTP with `FLASK_ENV=production` you will silently
never receive a session cookie and login will appear to do nothing.

To run the dev overlay under Docker instead — bind-mounting your working tree
for hot reload — pass it explicitly. It is deliberately *not* named
`docker-compose.override.yml`, so it can never be applied by accident:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### Production deployment

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Before going live, work through this list:

- [ ] `.env` contains a unique 64-hex-character `SECRET_KEY` and `RUNNER_SECRET`. Never reuse them across environments.
- [ ] `FLASK_ENV=production` — this is what enables `Secure` on session cookies.
- [ ] TLS certificates are in `deploy/ssl/`, and `deploy/nginx/nginx.conf` points at them. Both directories are git-ignored.
- [ ] `HOST_INSTANCE_DIR` is an absolute path **on the host**, and it is backed up.
- [ ] `PASSKEY_RP_ID` and `PASSKEY_ORIGIN` are set to your real domain (see below) — otherwise passkeys silently fail to verify.
- [ ] The runner's port 32526 is bound to `127.0.0.1` only. Confirm with `docker compose ps`.
- [ ] Ports 10000–11999 are open at the firewall but **not** proxied through a CDN.
- [ ] You have read [`audit-docs/security-audit.md`](audit-docs/security-audit.md) and triaged the Critical and High findings. Several of them are exploitable by any registered user.

#### Challenge hostnames

Challenge containers bind host ports in the 10000–11999 range and are reached
directly as `host:port`, bypassing the reverse proxy entirely. If you front the
site with Cloudflare, note that the free tier does not proxy non-standard
ports — so the challenge subdomains must be set to **DNS-only (grey cloud)**.

The runner hands each instance a random hostname from a fixed pool of seven
subdomains (`runner/main.py`, `SUBDOMAINS`). Point all of them at your server
with DNS-only A records. `deploy/cloudflare/worker.js` is an optional Worker
that redirects browsers to the main site when they hit a subdomain with no live
container behind it.

Set the hostnames players are shown with `CHALLENGE_HOST`, `NC_CHALLENGE_HOST`,
and `WEB_CHALLENGE_HOST`. If unset, the app falls back to the request's own
`Host` header.

---

## Configuration reference

All configuration is environment-based. Start from
[`.env.template`](.env.template).

| Variable | Required | Default | Purpose |
|---|:---:|---|---|
| `SECRET_KEY` | **yes** | — | Flask session signing key. **The app refuses to start without it.** Generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`. |
| `RUNNER_SECRET` | **yes** | `''` | Shared secret authenticating `web` → `runner`. The runner refuses to start without it; leaving it blank on the web side silently breaks every launch. |
| `DATABASE_URL` | no | `sqlite:////app/instance/ctf.db` | SQLAlchemy URL. Accepts a PostgreSQL DSN for larger deployments — see [`docs/database-and-admin.md`](docs/database-and-admin.md). |
| `FLASK_ENV` | no | *(unset)* | Anything other than `development` enables `Secure` on session and remember-me cookies. |
| `HOST_INSTANCE_DIR` | **in Docker** | `/opt/ctf/instance` | Absolute **host** path bind-mounted as `/app/instance`. The runner needs it to translate paths for child containers. |
| `RUNNER_URL` | no | `http://runner:32526` | Where the web tier reaches the sidecar. |
| `CHALLENGE_HOST` | no | request `Host` | Default hostname shown to players for instances. |
| `NC_CHALLENGE_HOST` | no | `CHALLENGE_HOST` | Override for Binary Exploitation (`nc`) instances. |
| `WEB_CHALLENGE_HOST` | no | `CHALLENGE_HOST` | Override for Web instances. |
| `PASSKEY_RP_ID` | no | `localhost` | WebAuthn Relying Party ID — **your bare domain**, e.g. `gym.example.com`. Not in `.env.template`; add it yourself. |
| `PASSKEY_ORIGIN` | no | `http://localhost:5050` | WebAuthn origin — **scheme + host**, e.g. `https://gym.example.com`. Must match exactly or every assertion is rejected. |

Non-environment limits worth knowing, all defined in code:

| Limit | Value | Defined in |
|---|---|---|
| Max request body | 300 MB | `config.py` (`MAX_CONTENT_LENGTH`) |
| Per-user pending-file quota | 250 MB | `app/routes/submissions.py` |
| Single submission file | 250 MB | `app/routes/submissions.py` |
| Web archive / PWN binary / misc file | 100 MB each | `app/routes/submissions.py` |
| Player solution upload | 100 MB | `app/routes/challenges.py` |
| Avatar upload | 5 MB | `app/routes/settings.py` |
| Community post image | 5 MB in, 1 MB stored as WebP | `app/routes/community.py` |
| Session lifetime | 24 hours | `config.py` |
| "Keep me logged in" | 30 days | `config.py` |
| Instance TTL / hard cap | 15 min / 60 min | `runner/main.py` |
| Per-instance resources | 128 MB, 0.25 CPU, 64 pids | `runner/main.py` |

If you raise the upload limits, raise `client_max_body_size` in your nginx
config to match, or players will get an opaque 413 from the proxy.

---

## Challenge authoring

### As an administrator

`/admin/challenges` → create a challenge with a title, description, category,
difficulty, point value, flag, and optional artifact. Flags must be
`CSIA{...}`. Tick **regex** to have the flag matched with `re.fullmatch` instead
of compared literally.

### As a player

`/submit-challenge` accepts the same fields plus file attachments, and lands the
challenge in the admin review queue. Approved submissions are marked
`[COMMUNITY]` on the challenge list; author-submitted files count against your
250 MB pending quota until they are approved.

### Packaging artifacts

| Category | Artifact | How it runs |
|---|---|---|
| **Web** | `.tar.gz` (required) | Extracted, runtime auto-detected, served on an allocated port. A single top-level directory is unwrapped automatically. |
| **Binary Exploitation** | ELF executable or `.tar.gz` (required) | Wrapped in `socat`; stdin/stdout are piped to the player's TCP connection. The runner looks for an entrypoint named `run`, `main`, `challenge`, `start`, or `server`, then falls back to the first executable file. |
| **Misc** | any file, or `.tar.gz` (required) | An archive is auto-detected like a Web challenge; a single file is served over `python -m http.server`. |
| Everything else | optional attachments | Downloaded from the challenge page; no instance is launched. |

### Dynamic flags

Put a file named `flag.txt` anywhere in your archive. On every launch the runner
overwrites **all** of them with a fresh `CSIA{<64 hex>}` unique to that player,
and records it so flag submission validates against the player's own value. The
literal flag you typed into the form becomes irrelevant for that challenge, so
put a placeholder in `flag.txt` in your source archive.

> [!NOTE]
> [`docs/roadmap.md`](docs/roadmap.md) records that the backend strips the
> dynamic flag from status responses but the frontend still writes it into the
> DOM and `localStorage`. Treat dynamic flags as obfuscation, not as a control,
> until that is fixed.

---

## Ranks, XP, and badges

### Percentile ranks

Your score is a weighted sum over solved challenges (easy ×1.0, medium ×2.2,
hard ×4.5) with contributions from accepted submissions and community activity.
`app/ranking.py` computes every player's score in one batched pass, caches it on
Flask's `g`, and maps your percentile onto a tier:

| Percentile | Title |
|---|---|
| Top 0.1% | Master of the Nexus |
| Top 1% | Digital Overlord |
| Top 3% | Grid Phantom |
| Top 6% | System Sage |
| Top 10% | Quantum Hacker |
| Top 20% | Cipher Hunter |
| Top 35% | Scriptblade |
| Top 50% | Packet Rogue |
| Top 75% | Firewall Adept |
| Everyone | Neo Initiate |

Each tier carries its own CSS treatment, and they escalate — `Neo Initiate` is
flat grey, `Packet Rogue` animates a fire gradient, `Cipher Hunter` flickers its
letter-spacing, and the top tiers layer multiple `drop-shadow` filters over a
moving gradient. Click your rank anywhere on the site to open `/ranks` for the
full table and lore.

### Legendary ranks

Five titles sit **outside** the percentile system and override it entirely.
`/ranks` lists them with an "origin" column. See [Easter eggs](#easter-eggs) —
three of the five are not obtainable through the UI, and that is on purpose.

### Badges

Badges have a title, description, image, a **border tier from 1 to 10**
(tier 1 is flat grey; tier 10 is a rotating rainbow gradient), an optional
limited-edition count shown as `#3/50`, and `from_event` / `is_unattainable`
flags. `/badges` lists every badge on the platform with how to earn it — click
any badge anywhere on the site to jump there and highlight it.

Seven automatic award rules are available: `solved_challenge`,
`community_posts`, `approved_submissions`, `post_upvotes`, `comment_reactions`,
`scoreboard_top_week`, and `top_month_post`. The eighth, `claimable_link`, is
the interesting one — see below.

---

## Easter eggs

> [!TIP]
> Spoilers follow. If you would rather find these yourself, stop reading and go
> look at `/ranks`.

### 🥇 `I4mGroot` — the Ghost in the Core

There is exactly one rank on this platform that **cannot be granted by anyone**.

Go to **`/ranks`**. Do not click anything. Just type:

```
I4mGroot
```

The page has a keystroke buffer listening the whole time you are there. Get all
eight characters in sequence — `Backspace` rewinds the buffer, so typos are
forgiven — and the browser fires `POST /api/ghost-unlock`. If the payload
matches, your account is permanently promoted to **Ghost in the Core**, a cyan
modal detonates across the viewport with `GHOST IN THE CORE — UNLOCKED`, and
the page reloads 4.6 seconds later wearing your new title.

Its description reads:

> *"You found the signal buried in the noise. The Ghost in the Core exists
> between layers — a phantom who discovered the hidden frequency and answered
> the call. This rank cannot be given. It can only be found."*

That is literally true. `ADMIN_ASSIGNABLE_LEGENDARY` contains only *Omninet
Ambassador* and *Omninet Sovereign*; the admin panel physically cannot assign
the other three.

<sub>`app/ranking.py:25` · `app/templates/ranks.html:273` · `app/routes/settings.py:142`</sub>

### 🔒 The ranks nobody can reach

The Legendary table on `/ranks` has an **origin** column, and two of its rows
are jokes at your expense:

- **Zero-Day Deity** — origin: `Dev Only`, in red. *"Before the patch. Before the disclosure. Before anyone knew the vulnerability existed — you were already there... Reserved for those who built what others can only use."* No route, form, or admin action assigns it. The only way in is a direct `UPDATE users SET legendary_rank` against the database. If you are reading the source to find the trick: that **is** the trick.

- **Singularity Architect** — origin: `???`, in white. The title itself renders as `???` on the page. Its description in `app/ranking.py` is the string `'???'`. There is no unlock condition anywhere in the codebase, because there is no unlock. It exists purely to sit at the top of the table, unexplained, forever.

### 🛡️ Ranks that outrank the admin

Once you hold *Ghost in the Core*, *Zero-Day Deity*, or *Singularity Architect*,
the admin panel **stops being able to touch your rank**. `/admin/users/<id>/edit`
replaces the rank dropdown with a purple notice reading *"This user holds a
protected legendary rank. It cannot be modified here."*, and the POST handler
refuses the change independently — so you cannot get around it with a crafted
request either.

Type eight characters on a public page and you acquire a property of your
account that the site owner cannot revoke through the UI.

<sub>`app/routes/admin.py:816` · `app/templates/admin/edit_user.html:129`</sub>

### ✝️ The apostles

Every challenge instance is assigned a random hostname from a hard-coded pool of
seven:

```
nathanael · thomas · peter · matthew · judas · james · andrew
        ... each at .chal.haucsia.com
```

Seven apostles. The platform was built for a society at **H**oly **A**ngel
**U**niversity — hence `haucsia.com` — and somebody decided the machines running
deliberately vulnerable code should be named after them. **Judas is in the
pool.** Draw your own conclusions about which subdomain you want your exploit
running on.

<sub>`runner/main.py`, `SUBDOMAINS`</sub>

### 🎫 Secret badge claim links

Admins can attach a `claimable_link` rule to any badge. Doing so mints a
`secrets.token_hex(32)` token — 64 hex characters, unguessable — and turns
`/claim/<token>` into a live URL that awards the badge to whoever visits it
while logged in.

Nothing on the site links to it. It is a scavenger-hunt primitive: drop the URL
in a Discord message, a conference slide, the last line of a writeup, or the
comments of a challenge nobody has solved yet. Combine it with a limited-edition
count and the badge becomes a race — visitor 51 gets *"Sorry — the badge is
sold out (limited edition)."*

<sub>`app/routes/admin.py:410` · `app/routes/challenges.py:429`</sub>

### 🚫 Badges designed to be impossible

Badge creation has two checkboxes that do nothing except change how the badge is
displayed to people who will never earn it: `from_event` and `is_unattainable`.
An unattainable badge renders on `/badges` with a red `UNATTAINABLE` pill.

It is a trophy case containing a locked cabinet.

### 🏆 Tier 10 — "god" border

Badge borders run from `tier1` to `tier10`. Tier 1 is a flat grey 3px line.
Tier 10 has a **transparent** border and a `::before` pseudo-element that paints
a five-stop `#ff0040 → #e040fb → #00fff7 → #facc15 → #ff0040` gradient at 300%
background-size, cycling through `rainbowShift` every two seconds behind the
badge. The intermediate tiers are named in the CSS class comments: *uncommon,
rare, epic, legendary, mythical, ancient, divine, celestial* — and then `bdGod`.

### 👻 Ghosting the scoreboard

Admins can flip `is_hidden_from_scoreboard` on any account. That player
disappears from `/scoreboard` — and their public profile at `/user/<id>`
starts returning a hard **404**, as if they had never existed. They can still
play, still solve, still score. They are simply unobservable.

### 🩸 First blood

The first three solvers of every challenge are recorded with their position and
shown a medal on the challenge list. The first solver additionally triggers a
site-wide `notify_first_blood` fan-out. There is no way to un-ring that bell —
and if an admin later deletes your correct submission, the scoreboard points and
the first-blood notification are both reverted.

### 🕵️ `Disallow: /`

`/robots.txt` is served from a route, not a static file, and its entire body is:

```
User-agent: *
Disallow: /
```

The whole platform asks every crawler on the internet to pretend it is not
there.

<sub>`app/routes/settings.py:70`</sub>

### 📜 Eggs in the commit history

The git log is its own changelog of small confessions:

| Commit | Message |
|---|---|
| `740a197` | *"Stop tracking me :("* — the commit that finally removed the live SQLite database from version control. It did not remove it from history; see [SEC-02](audit-docs/security-audit.md). |
| `21711f0` | *"Test version of the platform, please do not pull this commit"* — which is, at time of writing, the tip of `main`. |
| `71f945a` | *"Enabled hot-reloading to avoid constantly typing `docker system prune -af`."* |
| `fc4f86a` | *"Create .hidden"* — which creates a file named `.d`. |
| `96feb20` | *"Trying once more to resolve +solve challenge problem"* — one of seven consecutive commits fighting the same bug. |

The old `.gitignore` also carried a line for `.how2` — a personal notes file
that was diligently ignored and, as far as the history shows, never written.

---

## Operations

### Backups

Everything durable lives in `HOST_INSTANCE_DIR` (default `/opt/ctf/instance`):
the SQLite database, avatars, badge and milestone images, submission files,
challenge archives, player solution uploads, and the CSV audit log.

```bash
# Consistent database snapshot (does not require stopping the app)
docker compose exec web sqlite3 /app/instance/ctf.db ".backup '/app/instance/backup.db'"

# Everything, timestamped
tar czf "csiagym-$(date +%F).tar.gz" -C /opt/ctf instance
```

Restore by stopping the stack, replacing the directory, and starting again.

### Common tasks

```bash
# Follow logs for one service
docker compose logs -f web
docker compose logs -f runner

# Promote a user to admin without the UI
docker compose exec web python -c "
from app import create_app, db
from app.models import User
app = create_app()
with app.app_context():
    u = User.query.filter_by(username='alice').first()
    u.is_admin = True; db.session.commit(); print('ok')
"

# List live challenge containers
docker ps --filter 'name=chal_'

# Kill every challenge instance (the runner will not know; restart it after)
docker rm -f $(docker ps -q --filter 'name=chal_')
docker compose restart runner

# Full reset — DESTROYS ALL DATA
docker compose down -v && rm -rf /opt/ctf/instance/* && docker compose up --build
```

### Changing the port

Edit the `web` service in `docker-compose.yml`:

```yaml
ports:
  - "8080:5050"     # host:container
```

### Mobile access

`app/__init__.py` matches the `User-Agent` against a mobile regex and, for any
endpoint not on an explicit allowlist, serves `mobile.html` instead. Mobile
users can register, log in, read the scoreboard, use the community and mail,
and manage their account. Challenges, submissions, and the admin console are
desktop-only by design.

To open a page to mobile, add its endpoint name to `_MOBILE_ALLOWED`.

> [!NOTE]
> This is a user-agent check, not a security control. Spoofing the header
> bypasses it entirely — which is fine, because the pages behind it enforce
> their own authentication and authorization.

### Scaling

The default is SQLite with gunicorn running **one worker and four threads** —
deliberately, because SQLite and multiple writer processes do not mix. That
comfortably serves the ~100-player target. Past roughly 500 concurrent users,
move to PostgreSQL by pointing `DATABASE_URL` at it and raising the worker
count; [`docs/database-and-admin.md`](docs/database-and-admin.md) covers the
migration.

---

## Security posture

This platform **executes untrusted code by design**. Player-submitted archives
and binaries are extracted and run on your server. That is the product, not a
bug — but it means the isolation boundaries deserve scrutiny before you expose
an instance to the public internet.

**What is already in place:** CSRF protection via `CSRFProtect`, scrypt password
hashing through Werkzeug, `HttpOnly` / `SameSite=Lax` / conditionally `Secure`
cookies, HTML sanitisation with `bleach` on community posts, path-traversal
guards on every file-serving route, tar-extraction containment checks, WebAuthn
passkeys with sign-count replay detection, passkey-sudo on destructive admin
actions, per-container memory/CPU/PID limits, a CSV audit log, and a runner
sidecar bound to loopback and authenticated with `compare_digest`.

**What is not:** a full audit lives in
[`audit-docs/security-audit.md`](audit-docs/security-audit.md). Read it before
deploying. The findings that matter most:

| | Finding | Impact |
|---|---|---|
| 🔴 | **Stored XSS in comments** | Community comments are stored unsanitised and rendered with `\| safe`. Any registered user can run JavaScript in every viewer's browser, including admins'. Verified against a running instance. |
| 🔴 | **Live database in git history** | `instance/ctf.db` was tracked for most of the project's life. It is still recoverable from `main`, with password hashes and challenge flags. |
| 🔴 | **Docker socket mounted into the runner** | Any code execution in the runner is root on the host. |
| 🟠 | **Challenge containers run as root with network access** | No `cap_drop`, no `no-new-privileges`, `network_mode: bridge`. |
| 🟠 | **Security assertions written as `assert`** | Every WebAuthn origin, challenge, and RP-ID check disappears under `python -O` / `PYTHONOPTIMIZE`. |
| 🟠 | **No rate limiting anywhere** | Login, flag submission, mail, and image upload are all unthrottled. |

A prioritised, effort-estimated fix plan is in
[`audit-docs/remediation-plan.md`](audit-docs/remediation-plan.md).

### Reporting a vulnerability

Found something in CSIA GYM itself? Open a
[private security advisory](https://github.com/4ttth/CSIAGym/security/advisories/new)
rather than a public issue. Found something in a *challenge*? That is the point
— submit the flag.

---

## Documentation map

| Document | Read it when |
|---|---|
| [`docs/customization.md`](docs/customization.md) | Adding features or re-theming the platform |
| [`docs/database-and-admin.md`](docs/database-and-admin.md) | Working with the admin console, backups, or PostgreSQL |
| [`docs/file-attachments.md`](docs/file-attachments.md) | Understanding how challenge files are stored and served |
| [`docs/troubleshooting.md`](docs/troubleshooting.md) | Something is broken and you want the known fix |
| [`docs/roadmap.md`](docs/roadmap.md) | Checking whether a gap is known (it probably is) |
| [`WHATS-NEW.md`](WHATS-NEW.md) | Tracing when a feature landed — also served at `/whats-new` |
| [`audit-docs/`](audit-docs/) | Before deploying, and before planning the next sprint |

---

## Contributing

There is currently **no test suite, no CI, and no linter configuration** — the
first three items on
[`audit-docs/remediation-plan.md`](audit-docs/remediation-plan.md). Until that
changes, contributions are held to manual verification:

1. Branch from `main`.
2. Confirm the app still boots: `python -c "from app import create_app; create_app()"` with `SECRET_KEY` set.
3. Exercise the affected pages by hand, logged in as both a normal user and an admin.
4. Keep the house style — the codebase uses 4-space indent, single quotes in Python, and blueprint-local imports to avoid circular dependencies. Match the surrounding file.
5. Add an entry to `WHATS-NEW.md` under a new version heading. The app parses the version from the **first line** of that file, so keep the `* vX.Y.Z (Date)` format intact.

New routes that mutate state must either be covered by the global
`CSRFProtect` or call `validate_csrf` explicitly. Do not add `@csrf.exempt`
without one of the two — several existing endpoints get this wrong and are
findings in the security audit.

---

## License

Released under the [MIT License](LICENSE). © 2026 4ttth.

Third-party components — Flask, SQLAlchemy, Quill, particles.js, and the Docker
base images — remain under their own licences.

<div align="center">
<sub>Built with Flask and Docker. Brutalist design. Zero compromises.</sub>
</div>
