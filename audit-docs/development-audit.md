# Development audit

**Target:** CSIA GYM — commit `fc67d61`, branch `claude/nice-gauss-u9nl2q`
**Scope:** code quality, architecture, correctness, maintainability, tooling
**Findings:** 24 (3 critical, 6 high, 9 medium, 6 low)

Security findings are tracked separately in [`security-audit.md`](security-audit.md).

---

## 1. Codebase at a glance

| Metric | Value |
|---|---|
| Python source | 7,135 lines across 18 modules |
| Jinja templates | 9,323 lines across 42 templates |
| Registered routes | 140 |
| SQLAlchemy models | ~30 |
| Blueprints | 8 |
| Largest module | `app/routes/admin.py` — 1,443 lines |
| Largest template | `app/templates/challenges/detail.html` — 1,100+ lines |
| Automated tests | **0** |
| CI pipelines | **0** |
| Linter / formatter configuration | **none** |
| Migration framework | **none** — ~500 lines of hand-rolled bootstrap DDL |
| Dependency pinning | exact `==` pins throughout ✅ |

### What is genuinely good

Worth stating plainly, because the finding list below is long and the ratio
matters:

- **The blueprint decomposition is clean.** Eight blueprints with coherent, non-overlapping responsibilities. Cross-blueprint imports are deliberately function-local to dodge circular imports — an unusual pattern, but consistently applied and clearly intentional.
- **Every raw SQL statement is parameterised.** `app/routes/admin.py` drops to `text()` for bulk cascade deletes; all 24 of those statements bind with `:u` / `:c` placeholders. Not one f-string reaches a query.
- **`config.py` fails fast.** It raises at import time if `SECRET_KEY` is missing rather than falling back to a default. This is the correct behaviour and it is rarer than it should be.
- **`app/ranking.py` is well-engineered.** It batches all scoring queries into one pass and caches the result on Flask's `g`, so N callers in a request cost one query set. The module is documented and the intent is obvious.
- **The runner's containment checks are real.** `_safe_join`, `_extract_archive`, and `_inject_flag` (which uses `os.fwalk` with `dir_fd` to avoid TOCTOU on the flag write) all show someone who understood the attack they were defending against.
- **Dependencies are pinned exactly** and are current for the project's era.

The defects below are overwhelmingly the product of **missing feedback loops**,
not of poor judgement. There are no tests, so nothing catches a typo'd string
constant; there is no CI, so nothing catches an unreachable code path; there is
no linter, so `abort()` followed by dead code survives review.

---

## 2. Critical findings

### DEV-01 — No tests, no CI, no linting

**Severity:** Critical · **Assessed** · Affects the whole repository

There is no test suite, no CI workflow (`.github/` does not exist), no
`pyproject.toml` / `setup.cfg` / `.pre-commit-config.yaml`, and no linter
configuration of any kind.

For a 7,000-line application that authenticates users, runs untrusted code, and
handles a scoring system people care about, every change is verified by hand or
not at all. This is the **root cause** of at least five other findings in this
document — DEV-02, DEV-03, DEV-04, DEV-05, and DEV-07 are each the kind of
defect that a single smoke test or one `ruff` run would have caught before
merge.

The git history shows the cost directly. Seven consecutive commits —
`8c00d06`, `33ad79f`, `96feb20`, `c8a1b1b`, `16ff754`, `01eea13`, and
`4b89adc` — carry messages like *"Try to resolve problems with challenge"*,
*"Trying once more to resolve +solve challenge problem"*, and *"Last fix for
challenge solve hopefully"*. That is a debugging loop being run **through
production deploys** because there was no faster loop available.

**Fix:** [RP-01](remediation-plan.md#rp-01--establish-a-feedback-loop).

---

### DEV-02 — A fresh deployment cannot log in as admin

**Severity:** Critical · **Verified** · `app/__init__.py:596-606`

On first boot the app generates a random admin password and prints a banner —
but the banner never prints the password:

```python
_pw = _s.token_urlsafe(16)
admin = User(username='admin', email='admin@ctf.local', is_admin=True)
admin.set_password(_pw)
...
print("   Username: admin  |  Password: [see application startup log]", file=sys.stderr)
print(f"   Password hint: {_pw[:4]}{'*' * (len(_pw) - 4)}", file=sys.stderr)
```

Line 2 tells the operator to consult the startup log. **This is the startup
log.** The only other line emits the first four characters and masks the
remaining ~18, leaving roughly 2^100 of entropy to guess. `_pw` is then
discarded; nothing else reads it, and it is never written anywhere.

A brand-new deployment therefore has **no reachable administrator account**.
Recovery requires a manual `set_password()` through `docker compose exec`.

**Verified** during this audit — booting the app against a scratch database
produced exactly:

```
✅ Admin account created!
   Username: admin  |  Password: [see application startup log]
   Password hint: cY5m******************
```

**Likely history:** this reads like a security hardening pass that replaced a
hard-coded `admin123` (still documented in the pre-refactor README as the login)
with a random password, and masked the output without noticing that the mask
made the credential unrecoverable.

**Fix:** [RP-02](remediation-plan.md#rp-02--make-the-bootstrap-admin-reachable). One line, plus a first-login password change.

---

### DEV-03 — No migration framework; ~500 lines of bootstrap DDL run on every boot

**Severity:** Critical · **Confirmed by inspection** · `app/__init__.py:176-591`

`create_app()` calls `db.create_all()` and then executes roughly 500 lines of
hand-written forward-only migration on **every single application start**:

```python
user_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
for col, stmt in {
    'full_name':   'ALTER TABLE users ADD COLUMN full_name VARCHAR(120)',
    ...  # 17 more
}.items():
    if col not in user_cols:
        conn.execute(text(stmt))
conn.commit()
```

There are **three separate `PRAGMA table_info(users)` reads** (`user_cols` at
line 201, `user_cols2` at line 507, `user_cols3` at line 573) scattered through
the function, each guarding a different batch of columns added at a different
point in the project's history. The same pattern repeats for `challenges` (`ch_cols`,
`ch_cols2`), `community_posts` (`post_cols`, `post_cols2`), and
`challenge_submissions` (`sub_cols`, `sub_cols2`). Roughly 30 `commit()` calls
fire on every boot.

Consequences:

- **It is SQLite-specific.** The `PRAGMA table_info` idiom does not exist in PostgreSQL, so the documented "swap `DATABASE_URL` for PostgreSQL" upgrade path in [`docs/database-and-admin.md`](../docs/database-and-admin.md) **will not work** without rewriting this block.
- **Migrations are forward-only and unversioned.** There is no `alembic_version` equivalent, no rollback, and no way to know which schema a given database is at.
- **Nothing can ever be removed or renamed.** Dropping a column means editing the bootstrap and hoping every deployment already ran the old version.
- **It is a startup cost and a startup risk.** A partial failure mid-sequence leaves the schema in an undefined state, and the raw `CREATE TABLE IF NOT EXISTS` statements have silently drifted from the SQLAlchemy models they shadow.
- **One table has a nonsensical self-referential constraint.** `milestones` declares `FOREIGN KEY(id) REFERENCES milestones(id)` (`app/__init__.py:369`) — a row's primary key pointing at itself. Harmless in SQLite, which does not enforce it by default, but it signals the DDL was never reviewed.

**Fix:** [RP-05](remediation-plan.md#rp-05--adopt-alembic).

---

## 3. High-severity findings

### DEV-04 — Three incompatible category vocabularies; admin edit silently breaks PWN challenges

**Severity:** High · **Confirmed by inspection** · multiple files

`Challenge.category` is a free-text column with no whitelist validation on
write. Three different sets of values are in play, and they do not agree:

| Source | Values |
|---|---|
| Submission form<br>`app/templates/submissions/new.html:38-46` | `Web`, `Cryptography`, **`Binary Exploitation`**, `Reverse Engineering`, `Forensics`, `OSINT`, `Steganography`, `Networking`, `Misc` |
| Admin edit form<br>`app/templates/admin/edit_challenge.html:28` | `Web`, `Cryptography`, **`Binary`**, `Reverse Engineering`, `Forensics`, `OSINT`, `Steganography`, `Networking`, `Misc` |
| Runtime checks<br>`app/routes/challenges.py` | `'Web'`, `'Binary Exploitation'`, `'Misc'`, and **`'Web Exploitation'`** |

Two concrete defects fall out:

**(a) Editing a PWN challenge permanently breaks it.** The admin edit dropdown
offers `Binary`, and `edit_challenge` writes whatever arrives straight to the
column with no validation:

```python
challenge.category = request.form.get('category', '').strip()   # admin.py:759
```

But every runtime check wants the full string:

```python
if challenge.category != 'Binary Exploitation':   # challenges.py:483 — launch_nc
    ...
```

So an admin who opens a working Binary Exploitation challenge, changes nothing
but the title, and saves, silently rewrites the category to `Binary`. From that
moment `launch_nc` refuses to start an instance, and the on-solve container
teardown at `challenges.py:266` stops firing. The challenge looks fine in the
list and is simply unplayable. Nothing surfaces an error.

**(b) The Web Exploitation solution-file requirement is dead code.**
`challenges.py:310` and `:318` gate on `challenge.category == 'Web Exploitation'`,
a value no form can produce and no code path writes. The entire block — which
requires and stores a `.tar.gz` solution file for Web challenges, ~35 lines
including the `download_solution` route's whole reason to exist — is
**unreachable**.

**Fix:** [RP-04](remediation-plan.md#rp-04--unify-the-category-vocabulary).

---

### DEV-05 — Unreachable code after `abort()` in avatar upload

**Severity:** High · **Confirmed by inspection** · `app/routes/settings.py:226-232`

```python
try:
    validate_csrf(request.form.get('csrf_token'))
except ValidationError:
    abort(403)
    flash('No file selected', 'danger')        # ← unreachable
    return redirect(url_for('settings.index')) # ← unreachable
file = request.files['avatar']                 # ← KeyError if absent
```

Two defects in six lines:

1. `abort(403)` raises, so the two following statements can never execute. They are the remains of a missing-file check that was displaced when CSRF validation was added around it.
2. The missing-file check they were meant to perform **is now absent**. `request.files['avatar']` uses subscript access, so a POST without the field raises `KeyError` → HTTP 400 with no flash message, instead of the intended "No file selected".

Every other upload path in the codebase correctly uses `request.files.get(...)`.

**Fix:** [RP-03](remediation-plan.md#rp-03--correctness-quick-wins).

---

### DEV-06 — Dead route: the second-passkey flow cannot start

**Severity:** High · **Confirmed by inspection** · `app/routes/passkey.py:118-137`

```python
# ── Registration ───────────────────────────────────────────────
@login_required
@csrf.exempt
def verify_for_add_begin():
    ...
```

The function has `@login_required` and `@csrf.exempt` but **no
`@passkey_bp.route(...)` decorator**. Its sibling
`verify_for_add_complete` at line 141 has one. The begin half of the pair is
never registered.

The documented flow is: a user who already has a passkey must re-authenticate
with the existing one before adding a second. The `/begin` step that issues the
challenge is unreachable, so the front end cannot obtain a challenge, so
`/passkey/verify-for-add/complete` can only ever fail on
`session.pop('passkey_verify_add_challenge')` returning `None`.

**Net effect:** users can register a first passkey but not a second. There is no
error message — the flow simply does not start.

The decorator was almost certainly lost when the `# ── Registration ──`
separator comment was inserted above the function.

**Fix:** [RP-03](remediation-plan.md#rp-03--correctness-quick-wins). Add the missing decorator; verify the whole passkey flow end to end.

---

### DEV-07 — Runner instance state is in-memory only

**Severity:** High · **Confirmed by inspection** · `runner/main.py:88-90`

```python
_instances: dict[tuple[int, int], dict] = {}
_lock = threading.Lock()
```

Every live challenge instance — container ID, allocated port, assigned
subdomain, expiry, and the player's dynamic flag — lives in a process-local
dict. Nothing is persisted.

Restarting the runner (a deploy, a crash, an OOM kill, `restart: unless-stopped`
firing) loses the entire map. The consequences compound:

- **Containers orphan.** The reaper only iterates `_instances`, so containers it no longer knows about run forever, holding memory, CPU, and a port each.
- **Dynamic flags are lost.** The per-user flag lives only in this dict (and in the `dynamic_flags` table, written by the web tier at launch — so validation survives, but the runner can no longer report it).
- **Ports leak.** `_free_port()` computes `used` from `_instances`, so after a restart it will happily hand out a port that a surviving orphan still holds. `_port_free()` catches this with a bind test, but that is a TOCTOU race, not a fix.
- **Players lose their session.** Their instance is still running and reachable, but the platform reports no instance, and re-launching allocates a second container.

There is a partial mitigation at startup — it kills containers matching
`name=chal_` — but it is best-effort (`except Exception: log.warning(...)`) and
it destroys sessions that players are mid-way through.

All the state needed is already available from Docker itself: the containers
carry `chal.type`, `chal.challenge_id`, and `chal.user_id` labels. Rebuilding
`_instances` from `docker ps` on boot is the natural fix.

**Fix:** [RP-08](remediation-plan.md#rp-08--make-the-runner-restart-safe).

---

### DEV-08 — `app/routes/admin.py` is 1,443 lines

**Severity:** High · **Assessed** · `app/routes/admin.py`

One module holds the entire admin console: user management, challenge review,
badge design, badge rules, milestones, notifications, announcements, bug
reports, statistics, the audit log, and image processing for three different
upload types. It contains ~60 route handlers.

Concrete symptoms visible in the file:

- Five consecutive blank lines separate `edit_challenge` from `toggle_challenge_visibility` (lines 771-775) — one of several seams where unrelated features were appended over time.
- Helper functions (`_update_user_profile`, `_update_user_avatar`, `_update_user_badges`) are interleaved between route handlers rather than grouped.
- The audit-log writer, the IP resolver, image processing, and CSV export all live here alongside routing.
- Every other blueprint imports `log_event` *from* this module, making `admin.py` an unavoidable dependency of `auth`, `challenges`, `community`, and `submissions` — a 1,443-line module pulled in to get one 15-line function.

That last point is the real cost: it is not just large, it is **load-bearing in
the wrong direction**.

**Fix:** [RP-09](remediation-plan.md#rp-09--decompose-adminpy).

---

### DEV-09 — Two competing runner implementations shipped simultaneously

**Severity:** High → **Resolved in this refactor** · `app/web_runner.py`, `app/nc_runner.py`

Before this refactor, `app/` contained three challenge-execution
implementations:

| Module | Size | Status |
|---|---|---|
| `app/challenge_runner.py` | 121 lines | Live — HTTP client for the sidecar |
| `app/web_runner.py` | 19,759 bytes | Dead — subprocess + `unshare` |
| `app/nc_runner.py` | 16,702 bytes | Dead — subprocess + `socat` |

`challenge_runner.py`'s own docstring states it *"Replaces nc_runner.py and
web_runner.py entirely"*, yet both remained in the package, importable, and
carrying a completely different security model (host processes with `setrlimit`
and UID 1500, rather than containers).

Verified unreferenced — no module imports either; the only mentions were two
stale docstrings in `app/models.py:373` and `:392` that still describe the old
subprocess architecture.

**Action taken:** moved to `archive/legacy-runners/` with a
[README](../archive/README.md) explaining their status. They were not deleted
because they document the pre-Docker isolation model, which remains the
reference for how containment *should* behave.

**Remaining work:** update the two stale docstrings in `app/models.py`, and
delete the archived modules once [SEC-04](security-audit.md) is resolved.

---

## 4. Medium-severity findings

### DEV-10 — 31 CSRF-exempt state-changing endpoints with no compensating check

**Severity:** Medium (engineering) / High (security) · **Confirmed by inspection**

`@csrf.exempt` appears 37 times across `app/routes/`. Six of those are paired
with an explicit `validate_csrf(...)` call inside the handler — the correct
pattern when a route needs to accept both form and JSON bodies. The other
**31 are exempt with no compensating check at all**, including
`add_solve` (grants challenge credit), `remove_passkey` (deletes an
authentication factor), `ghost_unlock`, and all twelve instance
launch/stop/extend routes.

This is tracked as a security finding in
[SEC-07](security-audit.md); it appears here because the *engineering* problem
is that there is no convention. Whether a given route validates CSRF is
apparently decided per-route, with no rule a reviewer could apply and no lint to
enforce one.

**Fix:** [RP-06](remediation-plan.md#rp-06--codify-the-csrf-convention).

---

### DEV-11 — Broad `except Exception` swallowing failures silently

**Severity:** Medium · **Confirmed by inspection** · 13 occurrences

Thirteen `except Exception` handlers across `app/routes/admin.py` (4),
`app/routes/challenges.py` (5), and `runner/main.py` (4). The worst pattern
discards the exception entirely:

```python
# app/routes/challenges.py:277-283 — in _record_correct_solve
try:
    from app.challenge_runner import stop_server, stop_nc_server, stop_misc_server
    ...
except Exception:
    pass
```

A player solves a challenge; the teardown of their container fails; nothing is
logged; the container runs until the TTL reaper collects it — or forever, if the
runner has restarted (see [DEV-07](#dev-07--runner-instance-state-is-in-memory-only)).
The operator has no signal that anything went wrong.

The runner has the same pattern around container kills (`main.py:130-134`) and
leftover cleanup.

The codebase elsewhere gets this right — `app/__init__.py` catches
`(AttributeError, RuntimeError)` and `app/routes/auth.py` catches
`(OSError, AttributeError)` — so the narrow-catch convention exists; it is just
not applied consistently.

**Fix:** [RP-07](remediation-plan.md#rp-07--replace-silent-exception-swallowing).

---

### DEV-12 — No structured logging

**Severity:** Medium · **Assessed**

The web tier has no `logging` configuration. Diagnostics reach the operator
through:

- `print(..., file=sys.stderr)` — exactly once, for the admin bootstrap banner.
- A CSV audit log written with `csv.writer` (`app/routes/admin.py:48`), which records *business* events but not errors.
- Whatever gunicorn emits.

There is no request logging, no error logging, no way to correlate a user report
with a server-side event, and no log level to turn up when something breaks.
`runner/main.py` does configure `logging.basicConfig` — so the sidecar is
observable and the main application is not.

**Fix:** [RP-11](remediation-plan.md#rp-11--add-structured-logging).

---

### DEV-13 — The audit log is an append-only CSV file

**Severity:** Medium · **Confirmed by inspection** · `app/routes/admin.py:48-63`

Every audited event — across all five categories — appends a row to
`instance/admin_audit.csv`, opened and closed per write:

```python
with open(AUDIT_LOG, 'a', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    ...
```

Problems:

- **No rotation, no size cap.** The file grows without bound. Every login, logout, failed login, comment, post, and solve appends a row.
- **Concurrent writes are unserialised.** Gunicorn runs one worker with four threads, so four threads can `open(..., 'a')` the same file simultaneously. Small appends usually survive under `O_APPEND`, but this is not a guarantee, and it will produce interleaved rows under load.
- **It cannot be queried.** The admin log viewer reads the whole file, and paginates in JavaScript.
- **Reading it back is unvalidated**, and the values in it are attacker-influenced — see [SEC-09](security-audit.md) for the CSV-injection consequence.

Since the platform already has a database, an `AuditLog` model would fix
rotation, concurrency, and queryability at once.

**Fix:** [RP-12](remediation-plan.md#rp-12--move-the-audit-log-into-the-database).

---

### DEV-14 — `docker-compose.prod.yml` contains a vestigial port mapping

**Severity:** Medium · **Confirmed by inspection** · `docker-compose.prod.yml:6-9`

```yaml
ports:
  - "10000-10099:10000-10099"   # web challenge instances
  - "11000-11099:11000-11099"   # nc/RE challenge instances
```

These ranges belong to the **old subprocess model**, where challenge servers ran
inside the `web` container (`archive/legacy-runners/web_runner.py` declares
`PORT_RANGE_START = 10000`, `PORT_RANGE_END = 10099`). Under the current
architecture the runner sidecar starts *sibling* containers through the host
Docker daemon with `ports={f"{port}/tcp": ("0.0.0.0", port)}` — they bind host
ports directly and never traverse the `web` container.

So the mapping publishes 200 ports on `web` that nothing listens on, while the
actual range in use is 10000–11999 (`runner/main.py:56-57`) — wider than either
declared range and not reflected anywhere in the compose files.

The prod overlay also omits the `runner` service entirely, so
`-f docker-compose.yml -f docker-compose.prod.yml` works only because the base
file supplies it. That is fragile but functional.

**Fix:** [RP-13](remediation-plan.md#rp-13--clean-up-deployment-configuration).

---

### DEV-15 — Docker image builds nsjail from an unpinned git clone

**Severity:** Medium · **Confirmed by inspection** · `Dockerfile:27-32`

```dockerfile
RUN git clone --depth=1 https://github.com/google/nsjail.git /tmp/nsjail \
    && cd /tmp/nsjail && make -j$(nproc) ...
```

`--depth=1` with no `--branch` pulls whatever the default branch's HEAD is at
build time. Builds are not reproducible — two builds a week apart can produce
different binaries — and the build depends on GitHub being reachable and on
upstream not breaking the build.

Worse, the artifact is unused. `nsjail` is built, along with `bison`, `flex`,
`libprotobuf-dev`, `protobuf-compiler`, `libnl-route-3-dev`, `libcap-dev`, and a
`ctf-sandbox` user — all of which belong to the **superseded** subprocess
isolation model ([DEV-09](#dev-09--two-competing-runner-implementations-shipped-simultaneously)).
No Python module invokes it:

```console
$ grep -rn nsjail --include='*.py' app/ runner/
(no matches)
```

The only surviving references are in **user-facing copy**, which still tells
players they are protected by it:

| File | Text shown to users |
|---|---|
| `app/templates/submissions/new.html:119` | *"Each player gets their own isolated instance via `socat` + `nsjail`."* |
| `app/templates/index.html:361` | Feature tag: *"Docker · nsjail · socat"* |

Both claims are false under the current architecture — challenge isolation is
provided by Docker alone, and specifically by Docker with
[several protections disabled](security-audit.md#sec-04--challenge-containers-run-as-root-with-full-network-access).
Advertising a sandbox the platform does not use is worse than advertising
nothing.

The same image also installs `php-cli`, `nodejs`, `npm`, `ts-node`, `typescript`,
`default-jre`, and `socat` into the **web** tier — runtimes that only the
challenge containers need, since each one is launched from its own official
image. This inflates the web image by well over a gigabyte and expands its
attack surface for nothing.

**Fix:** [RP-14](remediation-plan.md#rp-14--slim-the-web-image).

---

### DEV-16 — Web container runs as root

**Severity:** Medium (engineering) / High (security) · `Dockerfile`

There is no `USER` directive. The image creates a `ctf-sandbox` user
(UID 1500) for the retired subprocess sandbox, then never switches to it, so
gunicorn runs as root.

Tracked as [SEC-06](security-audit.md).

---

### DEV-17 — Documentation contradicts the code it documents

**Severity:** Medium · **Partly resolved in this refactor**

| Claim | Reality |
|---|---|
| Old `README.md`: *"Admin: `admin` / `admin123`"* | Bootstrap generates a random password (`app/__init__.py:597`). Fixed by the new README. |
| Old `README.md`: *"Extract and start: `unzip ctf-platform.zip`"* | Distributed as a git repository. Fixed. |
| Old `README.md`: quick start is `docker compose up` with no prerequisites | `SECRET_KEY` is mandatory — the app raises without it. Fixed. |
| `docs/database-and-admin.md`: PostgreSQL upgrade path | Blocked by the SQLite-only bootstrap DDL ([DEV-03](#dev-03--no-migration-framework-500-lines-of-bootstrap-ddl-run-on-every-boot)). **Still inaccurate.** |
| `app/models.py:373`, `:392`: *"managed by web_runner.py as a subprocess"* | Managed by the runner sidecar as a container. **Still inaccurate.** |
| `app/routes/auth.py:169-172`: *"TO EXTEND: add rate limiting"* | Never implemented ([SEC-08](security-audit.md)). |
| `PARTICLES_SETUP.md` | 0 bytes. Deleted in this refactor. |
| `deploy/nginx/nginx.conf.template` | Was 0 bytes, while both compose files mount a config derived from it — nginx would have crash-looped. Populated in this refactor. |

**Fix:** [RP-15](remediation-plan.md#rp-15--reconcile-remaining-documentation).

---

### DEV-18 — Templates carry the styling that `styles.css` should

**Severity:** Medium · **Assessed** · `app/templates/`

`app/static/css/styles.css` is 25 KB, but the templates total 9,323 lines and
are dominated by inline `style="..."` attributes. A single representative line
from `app/templates/admin/posts.html:93`:

```jinja
<button type="submit" style="padding:4px 12px;background:transparent;color:{% if post.comments_disabled %}#fb923c{% else %}#4ade80{% endif %};font-size:0.72rem;font-weight:700;text-transform:uppercase;border:1px solid {% if post.comments_disabled %}rgba(251,146,60,0.4){% else %}rgba(74,222,128,0.4){% endif %};border-radius:3px;cursor:pointer;">
```

The ten badge border tiers are defined **three times** — in
`app/templates/public_profile.html:10-28`, `app/templates/admin/badges.html:9-60`,
and again as a Python dict in `app/routes/settings.py:79-90`. Changing tier 7's
colour means editing three files in two languages.

The palette (`#8b0000`, `#cc0000`, `#f87171`, `#4ade80`, `#fb923c`, `#a78bfa`)
is hard-coded at hundreds of sites with no custom properties, which also makes
[`docs/customization.md`](../docs/customization.md)'s re-theming guidance far
harder to follow than it reads.

**Fix:** [RP-16](remediation-plan.md#rp-16--consolidate-styling).

---

## 5. Low-severity findings

### DEV-19 — Build artifacts and dead files were committed

**Severity:** Low · **Resolved in this refactor**

Twelve `.pyc` files across three `__pycache__/` directories were tracked,
including `__init__.cpython-39.pyc` — a Python 3.9 artifact in a project whose
Dockerfile pins 3.11, i.e. a cache from a developer's machine with a different
interpreter.

Also removed: `.Dockerfile.bak` (a superseded Dockerfile containing
`chmod 777 /app/instance`) and the empty `PARTICLES_SETUP.md`. The root
`.gitignore` now covers `__pycache__/`, `*.py[cod]`, `*.bak`, and virtualenvs.

---

### DEV-20 — The dev compose overlay was misnamed

**Severity:** Low · **Resolved in this refactor**

`docker-compose-override.yml` used a hyphen where Compose expects a dot. As
written it was inert — Compose only auto-loads `docker-compose.override.yml`.

Simply renaming it would have been *worse*: the file sets
`FLASK_ENV=development`, which disables `SESSION_COOKIE_SECURE` and
`REMEMBER_COOKIE_SECURE` (`config.py:23,27`), and bind-mounts the working tree
over `/app`. Auto-applying that to every `docker compose up` would silently
strip cookie security from production.

**Action taken:** renamed to `docker-compose.dev.yml` — explicitly opt-in via
`-f`, and documented as such in the README.

---

### DEV-21 — `docker-compose.prod.yml` declared an invalid version

**Severity:** Low · **Resolved in this refactor**

`version: '3.x'` was not a valid Compose file version — the schema expects a
concrete string like `'3.8'`. Compose V2 ignores the key entirely, so this was
cosmetic. Removed, since the key is obsolete in V2.

---

### DEV-22 — Vendored `particles.js` is unminified and unattributed

**Severity:** Low · **Assessed** · `app/static/js/particles.js`

43 KB of third-party library committed as readable source with no version
marker, no upstream URL, and no licence header. There is no way to tell which
release it is, whether it carries known issues, or how to upgrade it. It is also
the single largest file in `app/static/`.

The project has no front-end dependency management at all — Quill and any other
libraries are loaded from CDNs in templates with no integrity attributes.

---

### DEV-23 — TOCTOU race in runner port allocation

**Severity:** Low · **Confirmed by inspection** · `runner/main.py:164-183`

```python
def _port_free(port: int) -> bool:
    with socket.socket(...) as s:
        s.bind(("0.0.0.0", port))   # binds, then closes
        return True
```

The socket is closed when the `with` block exits, and the port is handed to
`docker run` afterwards. Between the two, another process — including a
concurrent launch from a second thread, since `_free_port` runs under `_lock`
but the subsequent `containers.run` does not — can take it.

With a 2,000-port range and a ~100-player cohort, collisions are unlikely but
not impossible, and the failure mode is an opaque Docker bind error surfaced to
the player. Retrying on `docker.errors.APIError` would make it self-healing.

---

### DEV-24 — Duplicated version-parsing logic

**Severity:** Low · **Confirmed by inspection**

The same regex extraction of the version from `WHATS-NEW.md`'s first line is
implemented twice, with identical logic and identical error handling:

- `app/__init__.py:14-23` — at import time, into module-global `_VERSION`
- `app/routes/auth.py:31-38` — `get_version()`, re-reading the file per call

The second is called on every registration to compose a welcome notification.
One should call the other.

---

## 6. Findings resolved by this refactor

| ID | Finding | Action |
|---|---|---|
| DEV-09 | Two dead runner implementations in `app/` | Moved to `archive/legacy-runners/` with a documented rationale |
| DEV-19 | `__pycache__`, `.Dockerfile.bak`, empty `PARTICLES_SETUP.md` committed | Removed; `.gitignore` rewritten to prevent recurrence |
| DEV-20 | `docker-compose-override.yml` misnamed and dangerous to auto-load | Renamed `docker-compose.dev.yml`, opt-in only |
| DEV-21 | Invalid `version: '3.x'` | Removed |
| DEV-17 | README documented `admin123`, a zip distribution, and no prerequisites | Replaced with an accurate README |
| — | Empty `nginx.conf.template` mounted by both compose files | Populated with a working template |
| — | Single-directory nesting (`ctf-platform/` containing everything) | Application promoted to the repository root |
| — | Five guides scattered at the app root | Grouped under `docs/` |
| — | `generate_secrets.py` wrote `.env` beside itself | Moved to `scripts/`, now resolves the repository root explicitly |

The refactor was verified by booting the application from the new layout: 140
routes registered and seven representative pages returned HTTP 200.

---

## 7. Summary

| ID | Finding | Severity | Status |
|---|---|---|---|
| DEV-01 | No tests, no CI, no linting | Critical | Open |
| DEV-02 | Fresh deployment cannot log in as admin | Critical | Open |
| DEV-03 | No migrations; 500 lines of boot-time DDL | Critical | Open |
| DEV-04 | Three incompatible category vocabularies | High | Open |
| DEV-05 | Unreachable code after `abort()` in avatar upload | High | Open |
| DEV-06 | Second-passkey flow has no route | High | Open |
| DEV-07 | Runner state is in-memory only | High | Open |
| DEV-08 | `admin.py` is 1,443 lines and load-bearing | High | Open |
| DEV-09 | Two competing runner implementations | High | **Resolved** |
| DEV-10 | 31 unguarded CSRF-exempt endpoints | Medium | Open |
| DEV-11 | Broad `except Exception` swallowing failures | Medium | Open |
| DEV-12 | No structured logging | Medium | Open |
| DEV-13 | Audit log is an unrotated CSV | Medium | Open |
| DEV-14 | Vestigial prod port mapping | Medium | Open |
| DEV-15 | nsjail built from unpinned git clone | Medium | Open |
| DEV-16 | Web container runs as root | Medium | Open |
| DEV-17 | Documentation contradicts code | Medium | Partly resolved |
| DEV-18 | Styling lives in templates, tiers defined 3× | Medium | Open |
| DEV-19 | Build artifacts committed | Low | **Resolved** |
| DEV-20 | Dev compose overlay misnamed | Low | **Resolved** |
| DEV-21 | Invalid compose version | Low | **Resolved** |
| DEV-22 | Vendored `particles.js` unattributed | Low | Open |
| DEV-23 | TOCTOU in port allocation | Low | Open |
| DEV-24 | Duplicated version parsing | Low | Open |

**Assessment.** This is a capable application built by someone with real
instincts for security and structure, operating without any of the tooling that
would let those instincts scale. The blueprint layout, the parameterised SQL,
the fail-fast config, and the containment checks in the runner are all better
than typical. What is missing is the *feedback loop*: no test would have let
DEV-02 ship, no linter would have let DEV-05 or DEV-06 through, and no type
checker would have allowed three spellings of the same category to coexist.

Fixing DEV-01 first is what makes the other 23 findings stay fixed. See
[`remediation-plan.md`](remediation-plan.md).
