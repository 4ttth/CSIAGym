# Remediation plan

A sequenced plan for the findings in [`security-audit.md`](security-audit.md)
and [`development-audit.md`](development-audit.md).

Work items are numbered `RP-A*` (security, urgent), `RP-B*` (security,
scheduled), and `RP-01`–`RP-16` (development). Estimates assume one developer
already familiar with the codebase.

---

## How to sequence this

```
┌─ PHASE 0 ─── BLOCKING ──────────────────────────────── ~1 day ──────────────┐
│  Do not run a public deployment until these are done.                        │
│  RP-A1  Sanitise comments            ~15 min   SEC-01  ← verified exploit    │
│  RP-A2  Purge and rotate             ~3 h      SEC-02  ← already happened    │
│  RP-A5  Restore CSRF coverage        ~2 h      SEC-07                        │
│  RP-A6  Add rate limiting            ~2 h      SEC-08                        │
│  RP-A7  Username validation + CSV    ~1 h      SEC-09  ← verified exploit    │
│  RP-02  Bootstrap admin reachable    ~10 min   DEV-02  ← blocks first login  │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
┌─ PHASE 1 ─── HARDENING ──────────────────────────────── ~1 week ────────────┐
│  RP-A3  assert → real checks         ~1 h      SEC-05                        │
│  RP-A4  Harden challenge containers  ~3 h      SEC-04                        │
│  RP-B1  Remove Docker socket access  ~1 d      SEC-03                        │
│  RP-B2  Drop privileges, slim image  ~4 h      SEC-06, DEV-15, DEV-16        │
│  RP-01  Tests, CI, linting           ~2 d      DEV-01  ← unblocks the rest   │
│  RP-03  Correctness quick wins       ~1 h      DEV-05, DEV-06                │
│  RP-04  Unify category vocabulary    ~2 h      DEV-04                        │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
┌─ PHASE 2 ─── STRUCTURAL ─────────────────────────────── ~3 weeks ───────────┐
│  RP-B3..B8  Remaining security items          SEC-10 … SEC-15               │
│  RP-05  Adopt Alembic                ~2 d      DEV-03                        │
│  RP-08  Runner restart safety        ~1 d      DEV-07                        │
│  RP-09  Decompose admin.py           ~2 d      DEV-08                        │
│  RP-12  Audit log → database         ~1 d      DEV-13, SEC-17               │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
┌─ PHASE 3 ─── QUALITY ────────────────────────────────── ongoing ────────────┐
│  RP-06, RP-07, RP-10, RP-11, RP-13, RP-14, RP-15, RP-16                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

> [!TIP]
> If you can only do one thing today, do **RP-A1**. It is a single function call
> in two places and it closes a verified, remotely exploitable stored XSS.

---

## Phase 0 — Blocking

### RP-A1 — Sanitise comment content

**Fixes** [SEC-01](security-audit.md#sec-01--stored-xss-in-community-comments) · **~15 min** · **Verified exploit**

Comments take the same path as posts but skip `bleach.clean`. Add it in both
places.

```python
# app/routes/community.py — add_comment, currently line 405
- content = request.form.get('content', '').strip()
+ raw_content = request.form.get('content', '').strip()
+ content = bleach.clean(raw_content, tags=ALLOWED_TAGS,
+                        attributes=ALLOWED_ATTRS, strip=True)
```

```python
# app/routes/community.py — edit_comment, currently line 355
- content = request.form.get('content', '').strip()
+ raw_content = request.form.get('content', '').strip()
+ content = bleach.clean(raw_content, tags=ALLOWED_TAGS,
+                        attributes=ALLOWED_ATTRS, strip=True)
```

Keep the emptiness check against the **sanitised** value, so a comment that is
nothing but stripped markup is rejected rather than stored blank.

**Backfill existing rows** — anything already stored is still live:

```python
# one-off, run inside an app context
from app import db
from app.models import Comment
import bleach
from app.routes.community import ALLOWED_TAGS, ALLOWED_ATTRS

for c in Comment.query.all():
    clean = bleach.clean(c.content, tags=ALLOWED_TAGS,
                         attributes=ALLOWED_ATTRS, strip=True)
    if clean != c.content:
        c.content = clean
db.session.commit()
```

**Acceptance:** posting `<img src=x onerror=alert(1)>` as a comment stores
`<img src="x">`; `GET /community/<id>` contains no `onerror`. Add this as the
first regression test under [RP-01](#rp-01--establish-a-feedback-loop).

**Also consider:** long term, replace `| safe` with a Jinja filter that
sanitises at render time. Sanitising on write means a future allowlist change
does not retroactively protect stored rows.

---

### RP-A2 — Purge the committed database and rotate everything in it

**Fixes** [SEC-02](security-audit.md#sec-02--live-sqlite-database-committed-to-git-history) · **~3 h** · **Verified**

Order matters. **Rotate before purging** — the purge is the slow, disruptive
part, and it does not help anyone who already cloned.

**Step 1 — Rotate (do this first).**

- [ ] Rotate **every challenge flag** that has ever existed. Any flag in a committed snapshot is public. For static-flag challenges, edit them in `/admin/challenges`. Challenges using dynamic `flag.txt` flags are unaffected, since those are generated per launch.
- [ ] Force a password reset for every account that existed during the affected commit range (`71f945a` … `740a197`). There is no password-reset flow (`app/routes/auth.py` lists it under `TO EXTEND`), so this currently means an admin-driven `set_password` and an out-of-band notification.
- [ ] Rotate `SECRET_KEY` and `RUNNER_SECRET`, which invalidates all sessions.
- [ ] Confirm no TLS private key ever entered history: `git log --all --diff-filter=A --name-only | grep -iE '\.(key|pem)$'` — currently returns nothing. ✅

**Step 2 — Purge history.**

```bash
pip install git-filter-repo
git clone --mirror https://github.com/4ttth/CSIAGym.git csiagym-mirror
cd csiagym-mirror
git filter-repo --invert-paths --path ctf-platform/instance/ctf.db
git push --force --all && git push --force --tags
```

**Step 3 — Contain the fallout.**

- [ ] Ask GitHub Support to expire cached views of the removed blobs. Force-pushing does not immediately purge them from GitHub's object store.
- [ ] Notify every collaborator to re-clone. Old clones still hold the blob, and a subsequent push re-introduces it.
- [ ] Delete any forks you control.

**Step 4 — Prevent recurrence.** The rewritten `.gitignore` now covers
`instance/`, `*.db`, `*.sqlite`, and `*.sqlite3`. Add a pre-commit hook:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks: [{ id: gitleaks }]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-added-large-files
        args: ['--maxkb=500']
```

**Acceptance:** `git log --all --diff-filter=A --name-only | grep ctf.db`
returns nothing on a fresh clone, and all pre-existing flags have been changed.

---

### RP-A5 — Restore CSRF coverage

**Fixes** [SEC-07](security-audit.md#sec-07--31-csrf-exempt-state-changing-endpoints), [DEV-10](development-audit.md) · **~2 h**

31 state-changing endpoints are `@csrf.exempt` with no compensating check.

**Establish one rule:** a route may be `@csrf.exempt` *only* if it calls
`validate_csrf` itself. Nothing else.

Work in priority order:

1. **`add_solve`** (`challenges.py:286`) — highest impact, grants challenge credit. It reads both JSON and form data, so it has no preflight protection at all.
2. **`remove_passkey`** (`passkey.py:398`) — uses `get_json(force=True)`, so a `text/plain` POST is parsed and no preflight applies.
3. **All nine `launch_*` / `stop_*` / `extend_*`** routes (`challenges.py`) — resource exhaustion.
4. **`upload_image`** (`community.py:88`) — pairs with [RP-B5](#rp-b5--quota-image-uploads).
5. **The remainder** — `vote_challenge`, `toggle_bookmark`, `toggle_subscribe`, `react_comment`, `toggle_post_subscribe`, `ghost_unlock`, `tour_done`, and the four notification read-markers.

For fetch-driven JSON endpoints, send the token as a header and validate it:

```python
# add near the top of each blueprint, or in a shared app/security.py
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError

def require_csrf():
    token = (request.form.get('csrf_token')
             or request.headers.get('X-CSRFToken')
             or (request.get_json(silent=True) or {}).get('csrf_token'))
    try:
        validate_csrf(token)
    except ValidationError:
        abort(403)
```

Front-end side — the token is already in the DOM on every page:

```js
const csrf = document.querySelector('meta[name="csrf-token"]').content;
fetch(url, { method: 'POST', headers: { 'X-CSRFToken': csrf, ... } });
```

Add `<meta name="csrf-token" content="{{ csrf_token() }}">` to
`app/templates/base.html` if it is not already present.

**Passkey routes need care.** They are exempt because they exchange JSON.
`/passkey/auth/begin` and `/passkey/auth/complete` run **pre-login**, where
there is no session to bind a token to — those two can stay exempt (the WebAuthn
challenge in the session is itself the anti-replay token). Every other passkey
route runs authenticated and must validate.

**Acceptance:** `grep -rn 'csrf.exempt' app/routes/` returns only routes whose
body calls `validate_csrf` / `require_csrf`, plus the two documented pre-login
passkey endpoints with a comment explaining why.

---

### RP-A6 — Add rate limiting

**Fixes** [SEC-08](security-audit.md#sec-08--no-rate-limiting-anywhere) · **~2 h**

```bash
pip install Flask-Limiter==3.8.0   # add to requirements.txt
```

```python
# app/__init__.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["600 per hour"],
    storage_uri="memory://",   # single worker today; use redis:// if you scale out
)
# ... inside create_app():
limiter.init_app(app)
```

Apply per-endpoint:

| Endpoint | Suggested limit | Rationale |
|---|---|---|
| `auth.login` | `10/minute; 50/hour` | Brute force |
| `auth.register` | `5/hour` | Mass account creation |
| `challenges.submit_flag` | `20/minute` | Flag brute force, incl. regex search |
| `mail.compose` | `20/hour` | Mail bombing |
| `community.upload_image` | `30/hour` | Disk fill |
| `community.new_post`, `add_comment` | `30/hour` | Spam |
| `challenges.launch_*` | `10/hour` | Resource exhaustion |
| `passkey.auth_begin/complete` | `20/minute` | Assertion grinding |

> [!IMPORTANT]
> `get_remote_address` uses `request.remote_addr`, which behind nginx is the
> **proxy's** address — every user would share one bucket. Do
> [RP-B7](#rp-b7--trust-proxy-headers-correctly) (ProxyFix) **in the same
> change**, or rate limiting will either do nothing useful or lock out everyone
> at once.

Also: escalate repeated `login_failed` events in the audit log into a temporary
account lock. The events are already being recorded; nothing consumes them.

**Acceptance:** 11 rapid POSTs to `/login` return HTTP 429; a legitimate user
completing a normal session never sees one.

---

### RP-A7 — Validate usernames everywhere and neutralise CSV output

**Fixes** [SEC-09](security-audit.md#sec-09--csv-formula-injection-in-the-audit-log-reachable-via-unvalidated-username-change) · **~1 h** · **Verified exploit**

Two independent fixes; do both. Defence in depth matters here because the
formula executes on the **admin's workstation**, outside the platform.

**(a) Share one validator.** Registration validates; `/settings` does not.

```python
# app/validators.py  (new)
import re

USERNAME_RE = re.compile(r'^[A-Za-z0-9_]{1,32}$')
EMAIL_RE    = re.compile(r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')

def valid_username(v: str) -> bool:
    return bool(USERNAME_RE.match(v or ''))

def valid_email(v: str) -> bool:
    return bool(v) and len(v) <= 120 and bool(EMAIL_RE.match(v))
```

Call it from **both** `auth.register` and `settings.index`. Enforce the same
32-character cap and character class in both places, and validate the email on
update too — that handler currently checks uniqueness and nothing else.

**(b) Neutralise formulas on CSV write.**

```python
# app/routes/admin.py — in log_event, before writer.writerow(...)
def _csv_safe(value) -> str:
    s = '' if value is None else str(value)
    # Excel / LibreOffice / Sheets treat these as formula starts
    if s[:1] in ('=', '+', '-', '@', '\t', '\r'):
        s = "'" + s
    return s

writer.writerow([_csv_safe(v) for v in (
    timestamp, actor, action, target, category, ip_value)])
```

Apply the same wrapper to any other CSV export — check
`/admin/audit-log/download` and the statistics pages.

**(c) Backfill.** Existing usernames may already violate the rule. Report them
before enforcing, so you do not lock people out:

```python
from app.models import User
from app.validators import valid_username
bad = [u.username for u in User.query.all() if not valid_username(u.username)]
print(bad)
```

**Acceptance:** `POST /settings` with `username="=cmd|'/c calc'!A1"` is rejected
with a flash message; if such a value somehow reaches the log, the CSV cell
reads `'=cmd|...` and no spreadsheet evaluates it.

---

### RP-02 — Make the bootstrap admin reachable

**Fixes** [DEV-02](development-audit.md#dev-02--a-fresh-deployment-cannot-log-in-as-admin) · **~10 min** · **Verified**

```python
# app/__init__.py:601-604
- print("   Username: admin  |  Password: [see application startup log]", file=sys.stderr)
- print(f"   Password hint: {_pw[:4]}{'*' * (len(_pw) - 4)}", file=sys.stderr)
+ print(f"   Username: admin", file=sys.stderr)
+ print(f"   Password: {_pw}", file=sys.stderr)
+ print("   This is printed ONCE and never stored. Copy it now.", file=sys.stderr)
```

Printing a bootstrap credential to stderr once, on first boot, is the standard
pattern (Jenkins, Portainer, Sonarqube all do it). It is only reachable by
someone who can already read container logs — which is a higher privilege than
the account itself.

Better still, support an explicit override so nothing is printed at all:

```python
_pw = os.environ.get('ADMIN_BOOTSTRAP_PASSWORD') or _s.token_urlsafe(16)
```

**Follow-up (~2 h):** force a password change on first admin login. Add
`must_change_password` to `User`, set it on bootstrap, and add a
`before_request` hook that redirects to `/settings` until it is cleared.

**Acceptance:** a fresh `docker compose up` yields credentials that log in.

---

## Phase 1 — Hardening

### RP-A3 — Convert security assertions to real checks

**Fixes** [SEC-05](security-audit.md#sec-05--security-assertions-written-as-assert) · **~1 h**

Mechanical: replace all 15 `assert` statements in `app/routes/passkey.py` with
explicit conditionals that return a 400.

```python
- assert client_data['type'] == 'webauthn.get'
- assert client_data['challenge'] == challenge
- assert client_data['origin'] == ORIGIN
+ if client_data.get('type') != 'webauthn.get':
+     return jsonify(ok=False, error='Invalid client data type'), 400
+ if not secrets.compare_digest(str(client_data.get('challenge', '')), challenge):
+     return jsonify(ok=False, error='Challenge mismatch'), 400
+ if client_data.get('origin') != ORIGIN:
+     return jsonify(ok=False, error='Origin mismatch'), 400
```

Do all four handlers: `auth_complete`, `sudo_complete`, `register_complete`,
`verify_for_add_complete`. Then narrow the `except (KeyError, ValueError,
AssertionError)` clauses — `AssertionError` should no longer appear.

Add a guard so this cannot silently regress:

```python
# app/__init__.py, inside create_app()
if not __debug__:
    raise RuntimeError(
        'Refusing to start with assertions disabled (-O / PYTHONOPTIMIZE): '
        'security checks depend on them until RP-A3 is complete.'
    )
```

Remove that guard once the conversion is done and tested.

**Follow-up (~1 d):** migrate to [`py_webauthn`](https://github.com/duo-labs/py_webauthn).
The hand-rolled implementation also performs no attestation verification and
parses `authData` with unchecked fixed offsets (`passkey.py:264-270`).

**Acceptance:** `grep -c assert app/routes/passkey.py` returns 0; the full
passkey flow — register, authenticate, sudo, add second key — works end to end
under both `python` and `python -O`.

---

### RP-A4 — Harden challenge containers

**Fixes** [SEC-04](security-audit.md#sec-04--challenge-containers-run-as-root-with-full-network-access) · **~3 h**

Apply to all three call sites — `_build_web_container`, `_build_misc_container`,
`_build_nc_container` in `runner/main.py`:

```python
container = _docker.containers.run(
    image, command=cmd, detach=True,
    ports={f"{port}/tcp": ("0.0.0.0", port)},
    volumes={...},
    mem_limit=MEM_LIMIT, cpu_quota=CPU_QUOTA, cpu_period=CPU_PERIOD,
    pids_limit=PIDS_LIMIT,
+   user="65534:65534",                      # nobody:nogroup
+   cap_drop=["ALL"],
+   security_opt=["no-new-privileges:true"],
+   read_only=True,
+   tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
+   network=CHALLENGE_NETWORK,               # internal bridge, see below
-   network_mode="bridge",
-   read_only=False,
    ...
)
```

**Network isolation is the most valuable change here.** Create an internal
network once, at runner startup:

```python
# lifespan(), after _docker = docker.from_env()
CHALLENGE_NETWORK = "ctf-challenges"
try:
    _docker.networks.get(CHALLENGE_NETWORK)
except docker.errors.NotFound:
    _docker.networks.create(CHALLENGE_NETWORK, driver="bridge", internal=True)
```

`internal=True` removes outbound routing while leaving published ports
reachable from the host — which is what players need.

**Sequencing caution.** Web and Misc challenges currently run
`pip install -r requirements.txt` and `npm install` *at launch*
(`runner/main.py:256-284`), which requires egress. Do not flip the network
before addressing this, or every dependency-bearing challenge breaks. Two
options:

1. **Preferred:** install dependencies once, at challenge-approval time, into the stored archive, with egress; run the instance with none. Slower approval, faster and safer launches.
2. **Pragmatic:** add an `allow_network` boolean to the challenge model, defaulting to `False`, and let admins opt a challenge in.

`read_only=True` will break any challenge that writes outside `/tmp` — most
CTF web challenges do (SQLite files, upload directories, session stores). The
`/app` bind mount stays writable, so start there and widen only if needed.

**Roll out on a staging instance first.** This change *will* break some existing
challenges, and finding that out in production during a competition is the worst
possible time.

**Acceptance:** `docker exec <chal> id` reports `uid=65534`;
`docker exec <chal> ping -c1 8.8.8.8` fails; `docker exec <chal> capsh --print`
shows an empty capability set; the player-facing port still serves.

**Also:** fix the two UI strings that advertise `nsjail`
(`app/templates/submissions/new.html:119`, `app/templates/index.html:361`).
Describe the isolation you actually apply.

---

### RP-B1 — Remove direct Docker socket access

**Fixes** [SEC-03](security-audit.md#sec-03--docker-socket-mounted-into-the-runner) · **~1 d**

`/var/run/docker.sock` in a container that executes untrusted archives is
root-on-host, one bug away.

**Short term (~2 h) — socket proxy.** Put
[`tecnativa/docker-socket-proxy`](https://github.com/Tecnativa/docker-socket-proxy)
in front and grant only the endpoints the runner uses:

```yaml
  docker-proxy:
    image: tecnativa/docker-socket-proxy:0.1.1
    environment:
      - CONTAINERS=1      # list, inspect, create, kill, remove
      - IMAGES=1          # get, pull
      - NETWORKS=1        # for RP-A4's internal network
      - POST=1
      - EXEC=0            # ← blocks docker exec
      - INFO=0
      - VOLUMES=0
      - SWARM=0
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks: [internal]
    restart: unless-stopped

  runner:
    environment:
      - DOCKER_HOST=tcp://docker-proxy:2375
    # volumes: no longer mounts docker.sock
```

This does **not** eliminate the risk — `CONTAINERS=1` plus `POST=1` still allows
creating a privileged container with a host bind mount. It narrows the surface
and removes `exec`. Treat it as harm reduction, not a fix.

**Medium term (~1 d) — separate the parser from the launcher.** The runner does
two things with very different risk: (1) parse and inspect untrusted archives,
(2) call the Docker API. Split them. Move extraction, runtime detection, and
flag injection into an unprivileged worker with no Docker access; leave a
minimal launcher with a narrow, typed API surface (`launch(image, cmd, port,
volume)`) that validates every argument against an allowlist before calling
Docker.

**Long term — rootless Docker or Podman.** Run the daemon as an unprivileged
user so socket compromise is no longer host root. This is the only option that
actually closes the boundary.

**Acceptance:** the runner container has no `docker.sock` mount; challenges
still launch, stop, and reap correctly; `docker exec` through the proxy is
refused.

---

### RP-B2 — Drop privileges and slim the web image

**Fixes** [SEC-06](security-audit.md#sec-06--containers-run-as-root-the-web-image-ships-a-large-toolchain), [DEV-15](development-audit.md), [DEV-16](development-audit.md) · **~4 h**

The web tier ships `gcc`, `g++`, `make`, `git`, PHP, Node, npm, a JRE, `socat`,
`binutils`, and a locally built `nsjail` — none of which it uses. Challenge
runtimes come from their own images, started by the runner.

```dockerfile
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Pillow needs no build deps on manylinux wheels; keep this minimal.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd -u 1500 -m -s /usr/sbin/nologin ctfapp

COPY --chown=root:root . .
RUN rm -rf /app/.env /app/deploy/ssl /app/archive /app/audit-docs \
    && mkdir -p /app/instance \
    && chown -R ctfapp:ctfapp /app/instance

USER ctfapp
EXPOSE 5050
CMD ["gunicorn", "--workers", "1", "--threads", "4", \
     "--bind", "0.0.0.0:5050", "--timeout", "120", \
     "--max-requests", "500", "--max-requests-jitter", "50", "run:app"]
```

Notes:

- `COPY --chown=root:root` is kept deliberately: the app runs as `ctfapp` and cannot rewrite its own code. Only `instance/` is app-writable. This is what the original Dockerfile was reaching for.
- Removing nsjail removes `bison`, `flex`, `libprotobuf-dev`, `protobuf-compiler`, `libnl-route-3-dev`, `libcap-dev`, and the git clone in one go.
- Expect the image to shrink by well over a gigabyte.

**Migration note:** `HOST_INSTANCE_DIR` on the host must be writable by UID 1500
after this change, or the app cannot create the database. Document it, and
`chown -R 1500:1500 /opt/ctf/instance` on upgrade.

Pin base images by digest at the same time ([SEC-22](security-audit.md)):

```dockerfile
FROM python:3.11-slim@sha256:<digest>
```

**Acceptance:** `docker compose exec web id` reports `uid=1500(ctfapp)`; the app
boots, writes to `instance/`, and cannot write to `/app/app/routes/`.

---

### RP-01 — Establish a feedback loop

**Fixes** [DEV-01](development-audit.md#dev-01--no-tests-no-ci-no-linting) · **~2 d** · *unblocks everything else*

This is the highest-leverage development item. It is what makes the other fixes
stay fixed.

**Step 1 — tooling config.**

```toml
# pyproject.toml
[tool.ruff]
line-length = 110
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "B", "S", "UP", "C4", "SIM"]
ignore = ["E501"]
# S = flake8-bandit: flags assert-in-production (S101), which is SEC-05,
#     and broad except (S110), which is DEV-11.

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`ruff` with the `S` ruleset would have caught SEC-05 and DEV-11 automatically,
and `F` catches the unreachable code in DEV-05.

**Step 2 — a conftest that makes testing this app easy.**

```python
# tests/conftest.py
import os, secrets, pytest

os.environ.setdefault('SECRET_KEY', secrets.token_hex(32))

@pytest.fixture
def app(tmp_path):
    os.environ['DATABASE_URL'] = f"sqlite:///{tmp_path}/test.db"
    from app import create_app
    application = create_app()
    application.config['TESTING'] = True
    return application

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def user(app):
    from app import db
    from app.models import User
    with app.app_context():
        u = User(username='player', email='p@test.local')
        u.set_password('correct horse battery staple')
        db.session.add(u); db.session.commit()
        return u.username
```

> [!NOTE]
> `validate_csrf` raises on a missing token regardless of
> `WTF_CSRF_ENABLED`, so tests must scrape the real token out of the rendered
> form. Add a helper:
> ```python
> import re
> def csrf_token(client, path):
>     html = client.get(path).get_data(as_text=True)
>     m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
>     return m.group(1) if m else ''
> ```

**Step 3 — start with regression tests for confirmed findings.** Every test
below corresponds to a finding in this audit, so each one has a known-failing
starting state:

```python
def test_comment_content_is_sanitised(client, user):        # SEC-01
def test_settings_rejects_invalid_username(client, user):   # SEC-09
def test_audit_csv_neutralises_formulas():                  # SEC-09
def test_bootstrap_admin_password_is_printed(capsys):       # DEV-02
def test_avatar_upload_without_file_flashes(client, user):  # DEV-05
def test_verify_for_add_begin_is_routed(app):               # DEV-06
def test_challenge_categories_match_runtime_checks():       # DEV-04
def test_no_csrf_exempt_route_lacks_validation():           # SEC-07
```

That last one can be written as a static check over the route table, and it
prevents the whole class of finding from returning.

**Step 4 — CI.**

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11', cache: pip }
      - run: pip install -r requirements.txt pytest ruff
      - run: ruff check .
      - run: pytest -q
        env:
          SECRET_KEY: ${{ github.sha }}
      - name: Docker build
        run: docker build -t csiagym:ci .
```

**Acceptance:** CI runs on every push; `ruff check .` is clean; the regression
tests above pass; a PR reintroducing SEC-01 fails CI.

---

### RP-03 — Correctness quick wins

**Fixes** [DEV-05](development-audit.md#dev-05--unreachable-code-after-abort-in-avatar-upload), [DEV-06](development-audit.md#dev-06--dead-route-the-second-passkey-flow-cannot-start) · **~1 h**

**(a) Avatar upload** — `app/routes/settings.py:226-232`:

```python
  try:
      validate_csrf(request.form.get('csrf_token'))
  except ValidationError:
      abort(403)
- 	flash('No file selected', 'danger')
- 	return redirect(url_for('settings.index'))
- file = request.files['avatar']
+ file = request.files.get('avatar')
+ if not file or not file.filename:
+     flash('No file selected', 'danger')
+     return redirect(url_for('settings.index'))
- if not file.filename:
-     flash('No file selected', 'danger')
-     return redirect(url_for('settings.index'))
```

**(b) The missing passkey route** — `app/routes/passkey.py:119`:

```python
  # ── Registration ──────────────────────────────────────────────
+ @passkey_bp.route('/passkey/verify-for-add/begin', methods=['POST'])
  @login_required
  @csrf.exempt
  def verify_for_add_begin():
```

Then **test the whole passkey flow end to end** — register a first key,
authenticate with it, perform an admin sudo, and add a second key. The last of
these has never worked, so it has never been exercised.

Check the front-end fetch path too: `app/templates/settings.html` must call the
now-registered URL.

**Acceptance:** posting to `/settings/upload-avatar` with no file flashes
"No file selected" instead of returning 400; a user with one passkey can add a
second.

---

### RP-04 — Unify the category vocabulary

**Fixes** [DEV-04](development-audit.md#dev-04--three-incompatible-category-vocabularies-admin-edit-silently-breaks-pwn-challenges) · **~2 h**

Three spellings are in play and the admin edit form writes a fourth value
(`Binary`) that no runtime check recognises — silently bricking any PWN
challenge an admin edits.

**(a) One source of truth:**

```python
# app/constants.py  (new)
CATEGORY_WEB     = 'Web'
CATEGORY_PWN     = 'Binary Exploitation'
CATEGORY_MISC    = 'Misc'

CATEGORIES = (
    CATEGORY_WEB, 'Cryptography', CATEGORY_PWN, 'Reverse Engineering',
    'Forensics', 'OSINT', 'Steganography', 'Networking', CATEGORY_MISC,
)
LAUNCHABLE_CATEGORIES = (CATEGORY_WEB, CATEGORY_PWN, CATEGORY_MISC)

DIFFICULTIES = ('easy', 'medium', 'hard')
```

**(b) Drive both forms from it.** Pass `CATEGORIES` into
`app/templates/submissions/new.html` and `app/templates/admin/edit_challenge.html`
instead of hard-coding two divergent lists.

**(c) Validate on write** — `app/routes/admin.py:759`:

```python
- challenge.category = request.form.get('category', '').strip()
+ cat = request.form.get('category', '').strip()
+ if cat not in CATEGORIES:
+     flash('Invalid category.', 'danger')
+     return redirect(url_for('admin.edit_challenge', challenge_id=challenge_id))
+ challenge.category = cat
```

Do the same for `difficulty`, which is equally unvalidated.

**(d) Resolve the dead `'Web Exploitation'` branch** — `challenges.py:310,318`.
Decide whether the solution-file requirement for Web challenges was intended.
If yes, change the comparison to `CATEGORY_WEB` and **test it** — it has never
run. If no, delete the branch and the now-orphaned `download_solution` route
with it.

**(e) Repair existing data:**

```sql
UPDATE challenges SET category = 'Binary Exploitation' WHERE category = 'Binary';
```

Check for other drift first: `SELECT DISTINCT category FROM challenges;`

**Acceptance:** a test asserts every value in `CATEGORIES` is handled by the
launch routing or explicitly excluded; editing a PWN challenge through the admin
panel leaves it launchable.

---

## Phase 2 — Structural

### RP-B3 — Constrain regex flags

**Fixes** [SEC-10](security-audit.md#sec-10--redos-via-author-supplied-regex-flags) · **~3 h**

Author-supplied regexes are compiled against attacker-supplied input with no
timeout, on a four-thread worker.

Pick one, in order of preference:

1. **Swap the engine.** Use [`google/re2`](https://github.com/google/re2) via the `re2` Python binding — linear time, no catastrophic backtracking, no timeout needed. Cleanest fix; re2 does not support backreferences, which no reasonable flag pattern needs.
2. **Enforce a timeout.** Run the match in a worker with a hard deadline (a thread with a timeout, or `regex` module's `timeout=` parameter). Fails closed on a slow pattern.
3. **Validate at authoring time.** Reject patterns containing nested quantifiers (`(a+)+`, `(a*)*`), cap pattern length at ~200 characters, and test-compile against a generated worst-case input with a deadline before accepting the submission.

Do (3) regardless — rejecting a bad pattern at submission gives the author
immediate feedback instead of a mysterious outage later.

Also cap `submitted_flag` length before matching; there is currently no bound
beyond `MAX_CONTENT_LENGTH` (300 MB).

**Acceptance:** submitting `CSIA\{(a+)+b\}` as a regex flag is rejected at
authoring time; if such a pattern is already stored, a match attempt returns
within a bounded time rather than hanging a worker.

---

### RP-B4 — Extend passkey sudo coverage

**Fixes** [SEC-11](security-audit.md#sec-11--passkey-sudo-covers-an-incomplete-set-of-admin-actions) · **~2 h**

`_require_passkey_sudo()` is a good control applied to an arbitrary subset.
Invert the default: gate everything destructive, and list the exceptions.

Must be gated (currently are not):

- `promote_user` / `demote_user` — creates and removes administrators
- `make_moderator` / `remove_moderator`
- `assign_legendary`
- `create_badge_rule` — mints secret claim tokens
- `edit_challenge` — can rewrite a live flag
- `delete_challenge`, `delete_badge`, `delete_badge_rule`

A decorator is cleaner than per-route calls:

```python
from functools import wraps

def passkey_sudo_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _require_passkey_sudo():
            return _passkey_sudo_missing_response(request.referrer or url_for('admin.dashboard'))
        return fn(*args, **kwargs)
    return wrapper
```

Consider raising the 60-second window to ~5 minutes — a full moderation pass
currently requires re-tapping the key constantly, which trains admins to find it
annoying, which is how controls get removed.

**Acceptance:** every route in the list above returns the sudo-required redirect
without a fresh assertion; a test enumerates the admin blueprint and asserts
each destructive endpoint carries the decorator.

---

### RP-B5 — Quota image uploads

**Fixes** [SEC-12](security-audit.md#sec-12--unbounded-image-upload-storage) · **~3 h**

Apply the pattern that already exists for challenge submissions
(`_pending_usage` in `app/routes/submissions.py`):

- Add a `PostImage` model — `user_id`, `filename`, `file_size`, `post_id` (nullable), `created_at`.
- Enforce a per-user quota (50 MB is generous at ~1 MB per stored WebP).
- Delete orphaned images when their post is deleted, and reap images never attached to a post after 24 hours.
- Combine with the rate limit from [RP-A6](#rp-a6--add-rate-limiting) and CSRF from [RP-A5](#rp-a5--restore-csrf-coverage).

**Acceptance:** a user at quota receives a clear error; deleting a post removes
its images from disk.

---

### RP-B6 — Enforce a password policy

**Fixes** [SEC-13](security-audit.md#sec-13--no-password-policy) · **~2 h**

```python
# app/validators.py
MIN_PASSWORD_LENGTH = 12

def password_problems(pw: str) -> list[str]:
    problems = []
    if len(pw or '') < MIN_PASSWORD_LENGTH:
        problems.append(f'Password must be at least {MIN_PASSWORD_LENGTH} characters.')
    if len(pw or '') > 1024:
        problems.append('Password must be 1024 characters or fewer.')
    return problems
```

Follow current NIST guidance: **length over composition rules**. Do not require
mixed case and symbols — it produces `Password1!` and trains bad habits. Twelve
characters with no character-class rules is stronger in practice.

Add a breach check against the
[Pwned Passwords k-anonymity API](https://haveibeenpwned.com/API/v3#PwnedPasswords)
if the deployment has egress; it sends only a 5-character SHA-1 prefix, never
the password.

Apply in **both** `auth.register` and `settings.index`. Show a strength meter in
the UI.

**Acceptance:** registration with `a` is rejected; existing users are not locked
out (enforce on change, not on login).

---

### RP-B7 — Trust proxy headers correctly

**Fixes** [SEC-14](security-audit.md#sec-14--audit-log-trusts-client-supplied-ip-headers-unconditionally) · **~1 h** · *prerequisite for RP-A6*

```python
# app/__init__.py, inside create_app()
from werkzeug.middleware.proxy_fix import ProxyFix

# x_for = the number of proxies you actually run. One nginx = 1.
# Behind Cloudflare AND nginx = 2. Setting it too high lets clients spoof.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
```

Then simplify `_get_ip` — with `ProxyFix` in place, `request.remote_addr` is
already the real client:

```python
def _get_ip():
    return request.remote_addr or 'unknown'
```

If you front the site with Cloudflare, either set `x_for=2` *and* restrict
nginx to accept connections only from Cloudflare's published ranges, or keep the
`CF-Connecting-IP` read but validate the peer address against those ranges
first. An unvalidated `CF-Connecting-IP` read is worse than no header at all.

**Acceptance:** audit-log rows show real client IPs; sending
`CF-Connecting-IP: 8.8.8.8` from an arbitrary host does not change the logged
value.

---

### RP-B8 — Preserve symlinks on archive unwrap

**Fixes** [SEC-15](security-audit.md#sec-15--copytree-on-extracted-archives-dereferences-symlinks) · **~15 min**

```python
# runner/main.py:214
- shutil.copytree(inner, tmp)
+ shutil.copytree(inner, tmp, symlinks=True)
```

`symlinks=True` copies links as links instead of materialising their targets.

Stronger still — drop symlink members during extraction entirely, since no
legitimate challenge archive needs them:

```python
# runner/main.py, inside _extract_archive's member loop
+ if m.issym() or m.islnk():
+     continue
```

**Acceptance:** an archive containing `challenge/x -> /etc/passwd` produces
either a dangling link or no entry, never the file's contents.

---

### RP-05 — Adopt Alembic

**Fixes** [DEV-03](development-audit.md#dev-03--no-migration-framework-500-lines-of-bootstrap-ddl-run-on-every-boot) · **~2 d**

Replace ~500 lines of boot-time DDL with real migrations. This also unblocks the
PostgreSQL path that [`docs/database-and-admin.md`](../docs/database-and-admin.md)
already promises.

1. `pip install Flask-Migrate==4.0.7`; add to `requirements.txt`.
2. Reconcile `app/models.py` against the raw DDL in `app/__init__.py:176-591` — they have drifted, and the models are the version you want to keep.
3. `flask db init`, then `flask db migrate -m "baseline"` against an **empty** database. Review the generated migration by hand; autogenerate misses constraint changes.
4. For existing deployments, `flask db stamp head` so Alembic knows the schema is already current.
5. Delete the bootstrap block, keeping only the admin-user creation.
6. Add `flask db upgrade` to container startup, ahead of gunicorn.
7. Drop the nonsensical `FOREIGN KEY(id) REFERENCES milestones(id)` on `milestones` (`app/__init__.py:369`) in the first real migration.

**Test the upgrade path on a copy of production data before shipping.** This is
the highest-risk item in the plan: a bad migration loses the scoreboard.

**Acceptance:** a fresh database and an existing one both reach the same schema
via `flask db upgrade`; boot time drops noticeably; `DATABASE_URL` pointed at
PostgreSQL produces a working instance.

---

### RP-08 — Make the runner restart-safe

**Fixes** [DEV-07](development-audit.md#dev-07--runner-instance-state-is-in-memory-only) · **~1 d**

Everything needed to rebuild `_instances` is already on the containers — they
carry `chal.type`, `chal.challenge_id`, and `chal.user_id` labels.

**(a) Add the remaining state as labels at launch** — `chal.expires_at` and
`chal.subdomain`. The dynamic flag should *not* go in a label (labels are
world-readable to anything with Docker access); it already lives in the
`dynamic_flags` table, which is the right home.

**(b) Rebuild on startup** instead of killing everything:

```python
# lifespan(), replacing the current "kill leftovers" block
for c in _docker.containers.list(filters={"label": "chal.challenge_id"}):
    lbl = c.labels
    try:
        key = (int(lbl["chal.challenge_id"]), int(lbl["chal.user_id"]))
        _instances[key] = {
            "container_id": c.id,
            "port": int(lbl["chal.port"]),
            "subdomain": lbl.get("chal.subdomain"),
            "expires_at": float(lbl["chal.expires_at"]),
            "challenge_type": lbl["chal.type"],
        }
    except (KeyError, ValueError):
        log.warning("Unrecognised challenge container %s — killing", c.name)
        c.remove(force=True)
log.info("Recovered %d live instances after restart", len(_instances))
```

Players keep their sessions across a runner restart, the reaper regains
authority over every container, and ports stop leaking.

**(c) Fix the TOCTOU in port allocation** ([DEV-23](development-audit.md)) while
you are here: retry on `docker.errors.APIError` with a fresh port rather than
surfacing a bind failure.

**Acceptance:** launch an instance, `docker compose restart runner`, and confirm
`/status` still reports it as running with the correct expiry.

---

### RP-09 — Decompose `admin.py`

**Fixes** [DEV-08](development-audit.md#dev-08--approutesadminpy-is-1443-lines) · **~2 d**

1,443 lines, ~60 handlers, and — more importantly — every other blueprint
imports `log_event` from it, making it an unavoidable dependency of four other
modules.

**Do the cheap part first (~1 h):** extract `log_event`, `log_action`, and
`_get_ip` into `app/audit.py`. Update the five importing modules. This alone
removes the worst coupling and is low risk.

Then split the routes into a package:

```
app/routes/admin/
├── __init__.py       # blueprint + before_request guard, imports submodules
├── users.py          # ~400 lines
├── challenges.py     # ~250
├── badges.py         # ~300  (incl. milestones)
├── content.py        # ~200  (posts, bug reports)
├── notifications.py  # ~150  (notifications, announcements)
└── stats.py          # ~150  (dashboard, audit log viewer)
```

Keep one `admin_bp` in `__init__.py` so `url_for('admin.users')` and every
existing template link keeps working — this is a pure move, no URL changes.

Also extract the shared image-processing helpers (badge, milestone, and avatar
upload all reimplement crop-and-encode) into `app/image_utils.py`, which already
exists for exactly this.

**Do this after [RP-01](#rp-01--establish-a-feedback-loop).** Refactoring 1,443
lines of routing with no tests is how outages happen.

**Acceptance:** every admin URL resolves identically before and after; no module
is over ~400 lines.

---

### RP-12 — Move the audit log into the database

**Fixes** [DEV-13](development-audit.md#dev-13--the-audit-log-is-an-append-only-csv-file), [SEC-17](security-audit.md) · **~1 d**

The CSV has no rotation, no size cap, unserialised concurrent appends from four
gunicorn threads, and cannot be queried.

- Add an `AuditLog` model: `timestamp`, `actor`, `action`, `target`, `category`, `ip`, indexed on `(timestamp)` and `(category, timestamp)`.
- Rewrite `log_event` to insert a row.
- Server-side pagination and filtering in the admin viewer, replacing the current read-whole-file-and-paginate-in-JS approach.
- Keep CSV **export** — with the `_csv_safe` wrapper from [RP-A7](#rp-a7--validate-usernames-everywhere-and-neutralise-csv-output).
- Add a retention policy (e.g. 180 days) and a purge task.
- Cap `target` length on write; bug report `title`/`description` too ([SEC-17](security-audit.md)).

Write the migration to import the existing CSV so history is not lost.

**Acceptance:** audit events are queryable by category and date range; the log
viewer paginates server-side; export produces a CSV that no spreadsheet
evaluates.

---

## Phase 3 — Quality

### RP-06 — Codify the CSRF convention

**Fixes** [DEV-10](development-audit.md#dev-10--31-csrf-exempt-state-changing-endpoints-with-no-compensating-check) · **~2 h**

[RP-A5](#rp-a5--restore-csrf-coverage) fixes the 31 routes. This makes the fix
permanent:

- Document the rule in the README's contributing section (done) and in a short `CONTRIBUTING.md`.
- Add the static test from [RP-01](#rp-01--establish-a-feedback-loop) that walks `app.url_map`, finds every `@csrf.exempt` view, and asserts its source calls `validate_csrf` — with an explicit allowlist for the two pre-login passkey endpoints.

---

### RP-07 — Replace silent exception swallowing

**Fixes** [DEV-11](development-audit.md#dev-11--broad-except-exception-swallowing-failures-silently) · **~3 h**

Thirteen `except Exception` handlers, several with a bare `pass`. Fix the worst
first — `_record_correct_solve` (`challenges.py:277-283`), where a failed
container teardown is silently discarded:

```python
- except Exception:
-     pass
+ except (RuntimeError, requests.RequestException) as e:
+     current_app.logger.warning(
+         'Failed to stop instance for challenge %s user %s: %s',
+         challenge.id, user_id, e)
```

Never swallow without logging. Where a broad catch is genuinely correct — a
`before_request` hook that must not 500 the whole site — catch broadly, log at
`exception` level, and say why in a comment.

`ruff`'s `S110` (`try-except-pass`) and `BLE001` (blind except) flag these
automatically once [RP-01](#rp-01--establish-a-feedback-loop) lands.

---

### RP-10 — Remaining correctness nits

**Fixes** [DEV-22](development-audit.md), [DEV-23](development-audit.md), [DEV-24](development-audit.md), [SEC-16](security-audit.md), [SEC-18](security-audit.md), [SEC-19](security-audit.md), [SEC-20](security-audit.md), [SEC-21](security-audit.md) · **~4 h total**

| Item | Fix |
|---|---|
| SEC-16 | `secrets.compare_digest(submitted_flag, dyn.flag)` for literal flag comparison |
| SEC-18 | Require `next.startswith('/')`, reject `//` and `\` |
| SEC-19 | Pass a `bleach.css_sanitizer.CSSSanitizer`, or drop `style` from `ALLOWED_ATTRS` |
| SEC-20 | `os.environ['RUNNER_SECRET']` in `config.py` — fail fast like the runner does |
| SEC-21 | Add `PASSKEY_RP_ID` / `PASSKEY_ORIGIN` to `.env.template`; warn at startup if they are still `localhost` and `FLASK_ENV != development` |
| DEV-22 | Record `particles.js` version, upstream URL, and licence; add SRI to CDN `<script>` tags |
| DEV-23 | Retry port allocation on `docker.errors.APIError` (covered by [RP-08](#rp-08--make-the-runner-restart-safe)) |
| DEV-24 | Have `auth.get_version()` return `app._VERSION` instead of re-reading the file |

---

### RP-11 — Add structured logging

**Fixes** [DEV-12](development-audit.md#dev-12--no-structured-logging) · **~4 h**

The runner configures `logging`; the web tier does not. Add a `dictConfig` in
`create_app()`, log to stdout for container-native collection, and set the level
from an env var. Add request logging with a correlation ID so a user report can
be matched to a server-side event. Never log passwords, flags, session tokens,
or `RUNNER_SECRET`.

---

### RP-13 — Clean up deployment configuration

**Fixes** [DEV-14](development-audit.md#dev-14--docker-composeprodyml-contains-a-vestigial-port-mapping) · **~2 h**

- Delete the vestigial `10000-10099` / `11000-11099` mappings from `docker-compose.prod.yml` — challenge containers bind host ports directly through the runner, not through `web`.
- Document the real range (10000–11999, `runner/main.py:56`) as a firewall requirement rather than a compose mapping.
- Add the `runner` service to the prod overlay explicitly, or document that it must be composed with the base file.
- Add `healthcheck:` blocks to `web` and `runner` so `depends_on` waits for readiness rather than start.
- Add memory limits to the base compose, matching prod.

---

### RP-14 — Slim the web image

Covered by [RP-B2](#rp-b2--drop-privileges-and-slim-the-web-image).

---

### RP-15 — Reconcile remaining documentation

**Fixes** [DEV-17](development-audit.md#dev-17--documentation-contradicts-the-code-it-documents) · **~2 h**

The README has been rewritten and the empty files removed. Still outstanding:

- `docs/database-and-admin.md` describes a PostgreSQL upgrade path blocked by the SQLite-only bootstrap DDL. Either add the caveat now or update it after [RP-05](#rp-05--adopt-alembic).
- `app/models.py:373` and `:392` still describe `web_runner.py` / `nc_runner.py` as subprocess managers. Update to reference the runner sidecar.
- `app/routes/auth.py:78-81,169-172` — the `TO EXTEND` docstrings list rate limiting and password strength. Remove them as each is implemented.
- `app/templates/submissions/new.html:119` and `app/templates/index.html:361` advertise `nsjail`, which is not in use. Covered by [RP-A4](#rp-a4--harden-challenge-containers).
- `docs/roadmap.md` mixes done, partly done, and not started. Convert to GitHub issues and keep the file as an index, or mark statuses explicitly.

---

### RP-16 — Consolidate styling

**Fixes** [DEV-18](development-audit.md#dev-18--templates-carry-the-styling-that-stylescss-should) · **~1 week**

Incremental; no urgency, but it compounds.

1. Define CSS custom properties for the palette in `:root` — `--blood`, `--blood-bright`, `--danger`, `--success`, `--warn`, `--epic`.
2. Replace the ~hundreds of hard-coded hex literals, starting with the most-edited templates.
3. **Define the ten badge border tiers once.** They currently exist in `app/templates/public_profile.html:10-28`, `app/templates/admin/badges.html:9-60`, and `app/routes/settings.py:79-90` — three definitions in two languages. One CSS file, referenced by class name everywhere.
4. Extract repeated inline button, pill, and table styles into utility classes.
5. Only then does [`docs/customization.md`](../docs/customization.md)'s re-theming guidance become true.

---

## Tracking

| Phase | Items | Estimate | Gate |
|---|---|---|---|
| **0 — Blocking** | RP-A1, A2, A5, A6, A7, RP-02 | ~1 day | **Required before any public deployment** |
| **1 — Hardening** | RP-A3, A4, B1, B2, RP-01, 03, 04 | ~1 week | Required before a competition with stakes |
| **2 — Structural** | RP-B3–B8, RP-05, 08, 09, 12 | ~3 weeks | Required before scaling past the current cohort |
| **3 — Quality** | RP-06, 07, 10, 11, 13, 15, 16 | Ongoing | Continuous improvement |

### Suggested order for a single developer

```
Day 1     RP-A1 · RP-02 · RP-A7            (three verified defects, ~90 min total)
Day 1-2   RP-A2                            (rotate first, then purge)
Day 2-3   RP-A5 · RP-B7 · RP-A6            (CSRF, then ProxyFix, then limits — order matters)
Day 4-5   RP-01                            (tests + CI; regression-test everything above)
Week 2    RP-A3 · RP-A4 · RP-B2 · RP-03 · RP-04
Week 3    RP-B1 · RP-B8 · RP-B3 · RP-B6
Week 4+   RP-05 · RP-08 · RP-09 · RP-12, then Phase 3
```

Two ordering constraints worth repeating:

- **RP-B7 before RP-A6.** Rate limiting keyed on `request.remote_addr` behind an unconfigured proxy buckets every user together.
- **RP-01 before RP-09.** Do not refactor 1,443 lines of admin routing without tests.

### Definition of done

An item is done when the code is merged, a regression test covers it, the test
runs in CI, and — where the finding touched documentation — the docs agree with
the code.
