# Security audit

**Target:** CSIA GYM — commit `fc67d61`, branch `claude/nice-gauss-u9nl2q`
**Scope:** application code, challenge-execution sidecar, container and deployment configuration, git history
**Findings:** 23 (3 critical, 6 high, 8 medium, 6 low)

> [!IMPORTANT]
> Severity here reflects exploitability **by a registered, non-privileged user**
> against a public deployment. On a CTF platform that is the realistic attacker:
> you are inviting several dozen people who enjoy breaking software to create
> accounts and point their tooling at your server. "Only authenticated users can
> do this" is not a mitigation here — it is the baseline.

---

## 1. Threat model

### Assets

| Asset | Why it matters |
|---|---|
| Player credentials | Password hashes, emails, WebAuthn public keys. Reused passwords make this a liability beyond this platform. |
| Challenge flags | The entire competitive integrity of the platform. |
| Scoreboard and rank state | The thing players actually care about; also the basis for the Legendary ranks. |
| The host | The runner holds the Docker socket. Compromise here is root on the machine. |
| Other players' sessions | Admins browse the same community pages as everyone else. |

### Adversaries

| Adversary | Capability | Realistic goal |
|---|---|---|
| **Registered player** | Full authenticated surface: posts, comments, mail, uploads, challenge submissions, instance launches | Steal flags, inflate score, reach admin, escape a container |
| **Challenge author** | Everything above, plus arbitrary code uploaded as a challenge artifact and executed by the runner | Escape the challenge container, reach the platform, reach the host |
| **Unauthenticated visitor** | Login, registration, landing page, scoreboard, `/whats-new`, `/robots.txt` | Credential stuffing, account enumeration, DoS |
| **Compromised admin session** | The entire `/admin/*` surface | Total platform control |

### Trust boundaries

```
  internet ──▶ nginx ──▶ web (Flask)  ──▶ runner ──▶ docker.sock ──▶ HOST
                          │                   │                        ▲
              boundary 1 ─┘       boundary 2 ─┘          boundary 3 ───┘
              user input          shared secret,         ** none **
              authn/authz         loopback-only
```

- **Boundary 1** (user → web) is enforced by Flask-Login, `CSRFProtect`, and input validation. This is where most findings live.
- **Boundary 2** (web → runner) is enforced by `secrets.compare_digest` on a shared secret over loopback. This is **well built** — see [§5](#5-controls-that-are-working).
- **Boundary 3** (runner → host) **does not exist**. The runner has the Docker socket, and Docker socket access is root ([SEC-03](#sec-03--docker-socket-mounted-into-the-runner)).

---

## 2. Critical findings

### SEC-01 — Stored XSS in community comments

**Severity:** Critical · **Verified — exploit reproduced** · CWE-79
`app/routes/community.py:391-419`, `:343-368`; `app/templates/community/view.html:265`

Community **posts** are sanitised. Community **comments** are not. Both are
rendered with `| safe`.

```python
# new_post — community.py:177  ✅
content = bleach.clean(raw_content, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)

# add_comment — community.py:405  ❌
content = request.form.get('content', '').strip()
db.session.add(Comment(content=content, author_id=current_user.id, post_id=post_id))
```

```jinja
{# view.html:199 — sanitised upstream #}
<div id="post-body">{{ post.content | safe }}</div>

{# view.html:265 — NOT sanitised upstream #}
<div class="comment-body" ...>{{ comment.content | safe }}</div>
```

`edit_comment` (`community.py:355`) has the identical omission.

The `| safe` is there because comments are authored in a Quill rich-text editor
and legitimately contain HTML. The sanitiser that makes that safe was applied to
one of the two content types and not the other.

#### Reproduction

Verified against a locally booted instance during this audit:

```python
PAYLOAD = '<img src=x onerror="alert(document.domain)">'

# submitted to /community/new  → stored as:
'<img src="x">'                                    # ✅ onerror stripped by bleach

# submitted to /community/<id>/comment → stored as:
'<img src=x onerror="alert(document.domain)">'     # ❌ stored verbatim

# GET /community/<id> response body contains:
onerror="alert(document.domain)"                   # ❌ served verbatim
```

```
>> onerror handler present verbatim in served HTML: True
>> payload HTML-escaped instead                  : False
```

#### Impact

Any registered user can execute JavaScript in the browser of every person who
opens that post — including administrators and moderators, who visit community
pages as part of moderation.

Session cookies are `HttpOnly`, so the cookie itself cannot be read. That is a
real mitigation and it rules out simple session theft. It does **not** stop the
script from acting *as* the victim in their own browser:

- Fetch `/admin/users`, parse out a `csrf_token`, and POST `/admin/users/<id>/promote` to make the attacker an admin. Passkey sudo does **not** cover `promote_user` (`admin.py:148`) — see [SEC-11](#sec-11--passkey-sudo-covers-an-incomplete-set-of-admin-actions).
- Read any page the victim can read — including challenge pages showing flags — and exfiltrate it to an external host.
- Silently rewrite the victim's `/settings`, or send mail as them.

This is the single highest-impact finding in the audit, and the fix is one
function call in two places.

**Fix:** [RP-A1](remediation-plan.md#rp-a1--sanitise-comment-content). ~15 minutes including backfill of existing rows.

---

### SEC-02 — Live SQLite database committed to git history

**Severity:** Critical · **Verified — blob extracted from history** · CWE-312, CWE-540

`ctf-platform/instance/ctf.db` was tracked in version control across **ten
commits**, from `71f945a` through `2f894e7`, and was finally removed in
`740a197` — a commit titled *"Stop tracking me :("*.

Removing a file from the working tree does not remove it from history. The blob
remains reachable from `origin/main`:

```console
$ git cat-file -s $(git rev-parse 740a197^:ctf-platform/instance/ctf.db)
200704
```

Extracting and opening it confirms it is a real application database, not a
fixture:

```
TABLES: users, badges, milestones, challenges, challenge_submissions,
        community_posts, user_badges, notifications, ... (31 tables)
users row count      = 1
challenges row count = 2
user columns: id, username, email, password_hash, is_admin, ...
```

The `main` branch tip (`21711f0`, *"Test version of the platform, please do not
pull this commit"*) still carries this history.

#### Impact

Anyone who can clone the repository can recover:

- **Password hashes** for every account in the database at each of the ten snapshots. Werkzeug's scrypt makes these expensive to crack, not impossible — and a cracked password is likely reused elsewhere.
- **Challenge flags in plaintext**, from the `challenges.flag` column. On a live competition this is a total integrity failure; anyone with repository access wins.
- Email addresses and any profile data present at the time.

The snapshot inspected here holds one user and two challenges — small, and
plausibly a development database. **That does not resolve the finding.** Ten
snapshots were committed over six months of active development; the others must
be assumed to hold more. Any flag that ever appeared in a committed snapshot
should be treated as public.

#### Why this cannot be fixed by editing code

History rewriting (`git filter-repo`) removes the blob from *your* copy. It
cannot un-clone the repository from anyone who already has it, and it cannot
recall forks. **Rotate the secrets, do not merely hide them.**

**Fix:** [RP-A2](remediation-plan.md#rp-a2--purge-the-committed-database-and-rotate-everything-in-it). Rotate first, purge second.

---

### SEC-03 — Docker socket mounted into the runner

**Severity:** Critical · **Confirmed by inspection** · CWE-250, CWE-269
`docker-compose.yml:36`

```yaml
runner:
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
```

Write access to the Docker socket is **equivalent to root on the host**, without
qualification. Anyone holding it can start a privileged container with the host
filesystem bind-mounted at `/`:

```bash
docker run -v /:/host --privileged alpine chroot /host sh
```

No container boundary, no user namespace, and no capability set constrains this.

#### Why this matters more here than elsewhere

The runner is not an internal build tool. It is a service whose entire job is to
**ingest untrusted archives from users and execute them**. Its attack surface
includes `tarfile` extraction of attacker-controlled archives
(`runner/main.py:200-217`), runtime auto-detection driven by attacker-chosen
filenames (`:241-284`), and JSON parsing of an attacker-controlled
`package.json` (`:256-262`). Any memory-safety or logic bug in that path
converts directly into host root.

The chain is short and every link already exists:

```
player uploads a challenge archive
  → admin approves it
  → player launches it
  → runner extracts and inspects it
  → [any RCE in the runner]
  → docker.sock
  → root on the host
  → the platform database, every flag, every hash
```

#### Mitigations already present

The runner is bound to `127.0.0.1:32526` and authenticated with
`secrets.compare_digest`. Both are correct and they matter — they mean an
external attacker cannot simply call `/launch`. They do nothing about
code execution inside the runner process itself.

**Fix:** [RP-B1](remediation-plan.md#rp-b1--remove-direct-docker-socket-access). Put a socket proxy in front of it; longer term, move to a rootless or API-mediated launcher.

---

## 3. High-severity findings

### SEC-04 — Challenge containers run as root with full network access

**Severity:** High · **Confirmed by inspection** · CWE-250, CWE-923
`runner/main.py:295-335`, `:370-396`, `:436-460`

Every challenge container — running code an untrusted user uploaded — is
started with:

```python
_docker.containers.run(
    image, command=cmd, detach=True,
    ports={f"{port}/tcp": ("0.0.0.0", port)},
    volumes={_host_path(work_dir): {"bind": "/app", "mode": "rw"}, ...},
    mem_limit=MEM_LIMIT, cpu_quota=CPU_QUOTA, pids_limit=PIDS_LIMIT,
    network_mode="bridge",
    read_only=False,
    # no user=...
    # no cap_drop=...
    # no security_opt=...
)
```

What is missing:

| Control | State | Consequence |
|---|---|---|
| `user="nobody"` | absent | Challenge processes run as **root** inside the container |
| `cap_drop=["ALL"]` | absent | Full default capability set retained, including `CAP_NET_RAW`, `CAP_CHOWN`, `CAP_SETUID` |
| `security_opt=["no-new-privileges"]` | absent | setuid binaries can escalate within the container |
| `read_only=True` | explicitly `False` | Filesystem is writable |
| `network_mode="none"` or an internal network | `"bridge"` | **Full outbound internet, and reachability of every other container on the bridge** |

The resource limits (128 MB, 0.25 CPU, 64 pids) *are* set, which blunts
denial-of-service. Isolation is a different problem and is not addressed.

The `bridge` network is the sharpest edge. A challenge container can:

- Reach the internet — exfiltrate its own flag, download tooling, join a botnet, or make your server the origin of outbound abuse traffic.
- Reach other containers on the default bridge, including **other players' running challenge instances** — which hold *their* dynamic flags in `/app/flag.txt`.
- Attempt to reach the runner on `172.17.0.1:32526`. It does not have `RUNNER_SECRET`, so `/launch` rejects it — but this is one guessed secret away from [SEC-03](#sec-03--docker-socket-mounted-into-the-runner).

For Web and Misc challenges, the `pip install -r requirements.txt` and
`npm install` steps (`runner/main.py:256-284`) execute **attacker-authored
dependency manifests** as root with network access. That is arbitrary code
execution by design, in the least constrained configuration available.

#### Compounding: the UI claims a sandbox that is not in use

`app/templates/submissions/new.html:119` tells challenge authors:

> *"Each player gets their own isolated instance via `socat` + `nsjail`."*

and `app/templates/index.html:361` advertises *"Docker · nsjail · socat"*.
No Python module invokes `nsjail` — it belongs to the retired subprocess runner
(see [DEV-15](development-audit.md)). The platform advertises a hardening layer
it does not apply.

**Fix:** [RP-A4](remediation-plan.md#rp-a4--harden-challenge-containers). Roughly six keyword arguments; the network change needs per-challenge opt-in for challenges that genuinely need egress.

---

### SEC-05 — Security assertions written as `assert`

**Severity:** High · **Confirmed by inspection** · CWE-617
`app/routes/passkey.py` — 15 occurrences across four handlers

Every WebAuthn verification step is an `assert`:

```python
# auth_complete — passkey.py:335-344
client_data = json.loads(_b64url_decode(data['clientDataJSON']))
assert client_data['type'] == 'webauthn.get'
assert client_data['challenge'] == challenge          # replay protection
assert client_data['origin'] == ORIGIN                # phishing protection
auth_data = _b64url_decode(data['authenticatorData'])
assert auth_data[:32] == hashlib.sha256(RP_ID.encode()).digest()   # RP binding
assert flags & 0x01                                   # user-presence
```

Python removes every `assert` statement when the interpreter runs with `-O`, or
when `PYTHONOPTIMIZE` is set in the environment. Under those conditions this
code still *looks* like it verifies a passkey, and:

- the challenge is never compared → **replay of any captured assertion succeeds**
- the origin is never compared → **any site can drive an assertion against this RP**
- the RP ID hash is never compared → **credentials scoped to another RP are accepted**
- user presence is never checked

The `pub.verify(...)` signature check is a real function call and survives, so
an attacker still needs a valid signature over *some* challenge from *some*
credential. That reduces this from "trivially bypassable" to "replayable" — the
signature is not forgeable, but a single captured assertion becomes reusable
forever, and the phishing protections that make WebAuthn worth deploying are
gone.

Gunicorn does not set `-O` by default, so the default deployment is not
currently affected. That is the correct reading — and it is also exactly the
kind of assumption that breaks when someone adds `ENV PYTHONOPTIMIZE=1` to trim
image size. Authentication should not depend on an interpreter flag.

The same pattern gates `sudo_complete` (the admin re-authentication step),
`register_complete`, and `verify_for_add_complete`.

**Related:** the implementation is hand-rolled rather than using a reviewed
library. It performs no attestation verification, and `register_complete` parses
`authData` with fixed offsets and no length checks before slicing
(`passkey.py:264-270`) — a malformed `attestationObject` raises rather than
being rejected cleanly.

**Fix:** [RP-A3](remediation-plan.md#rp-a3--convert-security-assertions-to-real-checks). Mechanical; then plan migration to `py_webauthn`.

---

### SEC-06 — Containers run as root; the web image ships a large toolchain

**Severity:** High · **Confirmed by inspection** · CWE-250 · `Dockerfile`

The web image has **no `USER` directive**, so gunicorn runs as root. It creates
`ctf-sandbox` (UID 1500) for the retired subprocess sandbox and never uses it.

`COPY --chown=root:root . .` and `chown -R root:root /app/instance` are
deliberate — the intent was clearly "the app should not be able to modify its
own code". Running as root defeats it: root can write anywhere regardless of
ownership.

The image also ships `gcc`, `g++`, `make`, `git`, `php-cli`, `nodejs`, `npm`,
`ts-node`, `typescript`, `default-jre`, `socat`, `binutils`, and a
locally compiled `nsjail` — the full set of language runtimes and a compiler
toolchain, in the tier that holds the database and the session secret. None of
it is used by the web tier; challenge runtimes come from their own official
images.

Any RCE in the web tier therefore lands as root, with a compiler, an interpreter
for four languages, and `socat` already installed.

**Fix:** [RP-B2](remediation-plan.md#rp-b2--drop-privileges-and-slim-the-web-image).

---

### SEC-07 — 31 CSRF-exempt state-changing endpoints

**Severity:** High · **Confirmed by inspection** · CWE-352

`CSRFProtect` is initialised globally (`app/__init__.py:31`), which is correct.
It is then disabled on 37 routes with `@csrf.exempt`. Six of those compensate
with an explicit `validate_csrf(...)` call — the right pattern. **The other 31
have no CSRF protection at all.**

The exempt-and-unguarded set, enumerated:

| Module | Endpoints |
|---|---|
| `auth.py` | `tour_done` |
| `challenges.py` | `add_solve`, `vote_challenge`, `toggle_bookmark`, `toggle_subscribe`, and all nine `launch_*` / `stop_*` / `extend_*` routes |
| `community.py` | `upload_image`, `react_comment`, `toggle_post_subscribe` |
| `passkey.py` | all nine routes, including `remove_passkey` |
| `settings.py` | `ghost_unlock`, and the four notification read-markers |

Several are genuinely damaging:

- **`add_solve`** (`challenges.py:286`) — grants challenge credit to any named user, admin-only. A CSRF against a logged-in admin awards solves to the attacker. It accepts `request.form` as well as JSON, so a plain auto-submitting HTML form works; no CORS preflight is involved.
- **`remove_passkey`** (`passkey.py:398`) — deletes a victim's authentication factor. It reads the body with `force=True`, so a `text/plain` form POST is parsed as JSON and no preflight applies.
- **`launch_*`** — an attacker can force victims to spin up containers, exhausting the 2,000-port range and the host's memory.
- **`ghost_unlock`** (`settings.py:142`) — grants the hidden Legendary rank. Low impact, but it means the platform's marquee easter egg can be forced onto users who never found it.

The JSON-only routes get incidental protection from the browser's preflight
requirement — but only where `Content-Type: application/json` is genuinely
required. Handlers using `request.get_json(silent=True)` combined with
`request.form` fallbacks, or `force=True`, lose even that.

**Fix:** [RP-A5](remediation-plan.md#rp-a5--restore-csrf-coverage).

---

### SEC-08 — No rate limiting anywhere

**Severity:** High · **Confirmed by inspection** · CWE-307, CWE-770

There is no `Flask-Limiter`, no in-app throttle, and no rate limiting in
`deploy/nginx/nginx.conf.template`. Every endpoint accepts unlimited requests.

`app/routes/auth.py:169-172` documents the gap in a docstring:

```python
TO EXTEND:
- Add "Remember me" checkbox        # done
- Add rate limiting (prevent brute force)   # not done
- Add 2FA                                    # done, via passkeys
```

Two of the three were implemented. The one that was not is the one that matters
for an unauthenticated attacker.

| Endpoint | Unthrottled consequence |
|---|---|
| `POST /login` | Offline-free online password brute force. No lockout, no delay, no CAPTCHA. Registration enforces **no password complexity whatsoever** ([SEC-13](#sec-13--no-password-policy)), so short passwords are common. |
| `POST /challenges/<id>/submit` | Flag brute force. Acute for regex flags: a permissive author regex can be searched character by character. |
| `POST /register` | Mass account creation; scoreboard and percentile manipulation. |
| `POST /mail/compose` | Mail-bomb any user; each message also inserts a `UserNotification` row. |
| `POST /community/upload-image` | Unbounded disk fill — see [SEC-12](#sec-12--unbounded-image-upload-storage). |
| `POST /challenges/<id>/launch*` | Resource exhaustion: 2,000 ports, 128 MB each. |

`log_event` does record `login_failed` with a source IP, so the *evidence* of a
brute force is captured — nothing acts on it.

**Fix:** [RP-A6](remediation-plan.md#rp-a6--add-rate-limiting).

---

### SEC-09 — CSV formula injection in the audit log, reachable via unvalidated username change

**Severity:** High · **Verified — chain reproduced** · CWE-1236
`app/routes/admin.py:48-63`, `app/routes/settings.py:258-276`

Two separate weaknesses chain into one.

**Link 1 — registration validates usernames; `/settings` does not.**

```python
# auth.py:100 — registration  ✅
if not re.match(r'^[A-Za-z0-9_]{1,32}$', username):
    flash('Username must be 1–32 characters ...'); return redirect(...)

# settings.py:271 — profile update  ❌ uniqueness only
new_username = request.form.get('username', '').strip()
if new_username and new_username != current_user.username:
    if User.query.filter_by(username=new_username).first():
        flash('Username already taken', 'danger')
    else:
        current_user.username = new_username
```

Register with a compliant name, then change it to anything — any length, any
character, including leading `=`, `+`, `-`, `@`, and tab or CR.

**Link 2 — the audit log writes usernames into CSV unescaped.**

```python
writer = csv.writer(f)
writer.writerow([timestamp, actor, action, target, category, ip])
```

`csv.writer` quotes correctly for *CSV parsing*. It does nothing about
*spreadsheet formula evaluation*, which is a property of how Excel, LibreOffice,
and Google Sheets interpret a leading `=`.

#### Reproduction

Verified end to end during this audit:

```
username after POST /settings   : "=cmd|'/c calc'!A1"
register-time regex would allow : False
audit CSV last row              : 2026-09-18 09:00:14 UTC,=cmd|'/c calc'!A1,login_success,,auth,127.0.0.1
row begins with a formula       : True
```

An admin downloading the log from `/admin/audit-log/download` and opening it in
a spreadsheet gets a DDE prompt. Accepting it executes a command on the **admin's
workstation** — outside the platform's trust boundary entirely.

#### Secondary impacts of Link 1 alone

The username gap is independently serious, since usernames are identity:

- **Impersonation.** `admin ` (trailing space), `аdmin` (Cyrillic а, U+0430), or `admin<200b>` (zero-width space) are all distinct rows that render identically in most fonts. `filter_by(username=...)` is exact-match, so uniqueness does not help.
- **Layout injection.** No length cap — a 10,000-character username is accepted and rendered across the scoreboard, community, and admin tables.
- **Avatar divergence.** `_safe_filename` collapses `[^A-Za-z0-9_-]` to `_`, so `a.b` and `a_b` share `avatar_a_b.webp` — one user overwrites another's avatar.
- **No re-validation of email either** — same handler, same gap.

**Fix:** [RP-A7](remediation-plan.md#rp-a7--validate-usernames-everywhere-and-neutralise-csv-output).

---

## 4. Medium and low findings

### SEC-10 — ReDoS via author-supplied regex flags

**Severity:** Medium · **Confirmed by inspection** · CWE-1333
`app/routes/challenges.py:243-254`

```python
if challenge.is_regex:
    try:
        return bool(re.fullmatch(challenge.flag, submitted_flag))
    except re.error:
        return submitted_flag == challenge.flag
```

`challenge.flag` is author-controlled: a player ticks "regex" on
`/submit-challenge`, and the string is stored verbatim and compiled at
submission time. There is no complexity analysis and no timeout.

A pattern such as `CSIA\{(a+)+b\}` exhibits catastrophic backtracking. Since the
attacker also controls `submitted_flag`, they choose the input that maximises
it. Python's `re` has no timeout, and the web tier runs **one gunicorn worker
with four threads** — four concurrent submissions against such a challenge hang
the entire site.

Admin approval is the only gate, and a malicious regex is not obvious on
inspection. The `re.error` fallback catches *invalid* patterns, not *expensive*
ones.

**Fix:** [RP-B3](remediation-plan.md#rp-b3--constrain-regex-flags).

---

### SEC-11 — Passkey sudo covers an incomplete set of admin actions

**Severity:** Medium · **Confirmed by inspection** · CWE-862
`app/routes/admin.py:125-137`

`_require_passkey_sudo()` demands a WebAuthn assertion within the last 60
seconds. It is a genuinely strong control — and it is applied selectively.

`promote_user` (`admin.py:148`) — which grants **full administrator rights** —
is not among the gated actions. Neither are `create_badge_rule` (mints secret
claim tokens), `assign_legendary`, or `edit_challenge` (which can rewrite a live
flag).

Note the first line:

```python
if not current_user.passkeys:
    return False
```

This fails **closed**, which is correct. But callers pair it with
`_passkey_sudo_missing_response`, which merely flashes and redirects — so an
admin without a passkey is blocked from the gated actions and free to use the
ungated ones, including the one that creates more admins.

Combined with [SEC-01](#sec-01--stored-xss-in-community-comments), the
practical consequence is: XSS in a comment → victim admin's browser POSTs
`/admin/users/<attacker>/promote` → attacker is an admin, without ever touching
a passkey-gated route.

**Fix:** [RP-B4](remediation-plan.md#rp-b4--extend-passkey-sudo-coverage).

---

### SEC-12 — Unbounded image upload storage

**Severity:** Medium · **Confirmed by inspection** · CWE-770
`app/routes/community.py:88-104`

```python
@community_bp.route('/community/upload-image', methods=['POST'])
@login_required
@csrf.exempt
def upload_image():
    ...
    _, url = _convert_to_webp(file)
```

Per-request size is capped (5 MB in, ~1 MB stored as WebP). **Request count is
not.** There is no per-user quota, no total cap, no cleanup of images belonging
to deleted posts, and no rate limit. A loop of 5,000 uploads writes ~5 GB.

Images land in `app/static/post_images/`, which `docker-compose.yml` maps to the
named volume `post_images_data` — so filling it does not fill the instance
volume, but it does fill the Docker host's storage, which affects every
container.

Challenge submissions get this right: `_pending_usage()` enforces a 250 MB
per-user quota. The same pattern is simply absent here.

The route is also CSRF-exempt ([SEC-07](#sec-07--31-csrf-exempt-state-changing-endpoints)), so uploads can be
driven through a victim's browser.

**Fix:** [RP-B5](remediation-plan.md#rp-b5--quota-image-uploads).

---

### SEC-13 — No password policy

**Severity:** Medium · **Confirmed by inspection** · CWE-521
`app/routes/auth.py:96-110`, `app/routes/settings.py:278-286`

Registration checks that `password` is non-empty and matches `confirm_password`.
That is the entire policy. `a` is an accepted password. `/settings` password
changes apply no policy either.

The docstring at `auth.py:78-81` lists *"Add password strength requirements"*
under `TO EXTEND`. There is no breach-corpus check, no length minimum, and no
feedback in the UI.

With [SEC-08](#sec-08--no-rate-limiting-anywhere) (no rate limiting), a
single-character password is discovered on the first guess.

Hashing itself is correct — Werkzeug 3.0's `generate_password_hash` defaults to
scrypt.

**Fix:** [RP-B6](remediation-plan.md#rp-b6--enforce-a-password-policy).

---

### SEC-14 — Audit log trusts client-supplied IP headers unconditionally

**Severity:** Medium · **Confirmed by inspection** · CWE-348
`app/routes/admin.py:38-46`

```python
def _get_ip():
    return (
        request.headers.get('CF-Connecting-IP')
        or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        or request.remote_addr
        or 'unknown'
    )
```

Both headers are attacker-controlled unless a trusted proxy overwrites them.
Nothing verifies the request arrived through Cloudflare or nginx, and no
`ProxyFix` middleware is configured.

An attacker brute-forcing `/login` sets `CF-Connecting-IP: 8.8.8.8` and every
`login_failed` row in the audit log points at Google's resolver. The one
forensic record of an attack is attacker-controlled. If the IP is ever used for
blocking, this becomes an authorization bypass.

Also note `request.remote_addr` without `ProxyFix` returns the **proxy's**
address, so removing the headers naively would log nginx's container IP for
everything. The fix is `werkzeug.middleware.proxy_fix.ProxyFix` with an explicit
hop count.

**Fix:** [RP-B7](remediation-plan.md#rp-b7--trust-proxy-headers-correctly).

---

### SEC-15 — `copytree` on extracted archives dereferences symlinks

**Severity:** Medium · **Confirmed by inspection** · CWE-59
`runner/main.py:200-217`

`_extract_archive` guards traversal correctly — it normalises each member,
rejects `..`, and re-checks the resolved path against the destination. Then the
single-top-level-directory unwrap does this:

```python
entries = os.listdir(dest)
if len(entries) == 1 and os.path.isdir(os.path.join(dest, entries[0])):
    inner = os.path.join(dest, entries[0])
    tmp = dest + "_tmp"
    shutil.copytree(inner, tmp)        # symlinks=False (default) → FOLLOWS links
```

`shutil.copytree` defaults to `symlinks=False`, meaning it copies the **contents
of the symlink target**, not the link. An archive shaped as:

```
challenge/
challenge/notes.txt -> /etc/shadow
challenge/index.html
```

passes extraction (the symlink member itself is contained), then triggers the
unwrap, and `copytree` materialises the runner container's `/etc/shadow` into
the work directory — which is then bind-mounted into the challenge container at
`/app` and served by `python -m http.server`.

The reachable targets are files inside the **runner container**, not the host.
That container is minimal, so the yield is low — but it includes anything the
runner process can read, and the runner's environment (including
`RUNNER_SECRET`) is reachable through `/proc/self/environ` by the same trick.
Given [SEC-03](#sec-03--docker-socket-mounted-into-the-runner), leaking
`RUNNER_SECRET` is more serious than it first appears.

`shutil.copytree(inner, tmp, symlinks=True)` fixes it.

**Fix:** [RP-B8](remediation-plan.md#rp-b8--preserve-symlinks-on-archive-unwrap).

---

### SEC-16 — Non-constant-time flag comparison

**Severity:** Low · **Confirmed by inspection** · CWE-208
`app/routes/challenges.py:243-254`

```python
if dyn:
    return submitted_flag == dyn.flag
...
return submitted_flag == challenge.flag
```

Python's `str.__eq__` short-circuits on the first differing byte. In principle
this leaks a prefix oracle. In practice, network jitter over the internet
swamps a few-nanosecond difference, and the attacker would need enormous sample
counts — so the real-world risk is low.

It is listed because this is a **CTF platform**: some player will try it, and
`secrets.compare_digest` costs nothing.

---

### SEC-17 — Bug report descriptions are stored unvalidated

**Severity:** Low · **Confirmed by inspection** · `app/routes/settings.py:304-329`

`title`, `description`, and `page_url` are stored with no length cap and no
sanitisation. `severity` *is* whitelisted, which shows the author was thinking
about validation on that field and not the others.

`app/templates/admin/bug_reports.html:46` renders the description with
`white-space:pre-wrap` and **no `| safe`**, so Jinja autoescaping neutralises
HTML — this is not XSS. The issues are the missing length cap (unbounded rows,
admin-page layout destruction) and `page_url` being rendered as a link target
without scheme validation.

---

### SEC-18 — `login` redirect parameter is validated, with a narrow gap

**Severity:** Low · **Confirmed by inspection** · CWE-601
`app/routes/auth.py:191-196`

```python
next_page = request.args.get('next', '')
parsed = urlparse(next_page)
if next_page and not parsed.scheme and not parsed.netloc:
    return redirect(next_page)
```

This is **mostly correct** and blocks the common cases: absolute URLs
(`scheme` set) and protocol-relative `//evil.com` (`netloc` set) are both
rejected.

The gap is backslash handling. `urlparse('/\\evil.com')` yields an empty
`netloc`, so the check passes — but some browsers normalise `\` to `/` in URLs,
interpreting the result as `//evil.com`. Modern Chrome and Firefox do not
normalise it in the `Location` header, so this is largely theoretical today.

Recommend the belt-and-braces form: require `next_page.startswith('/')` and
`not next_page.startswith('//')` and `'\\' not in next_page`.

---

### SEC-19 — `style` attribute permitted in sanitised HTML

**Severity:** Low · **Confirmed by inspection** · `app/routes/community.py:27-33`

```python
ALLOWED_ATTRS = {
    'a': ['href', 'target', 'rel'],
    'span': ['class', 'style'],     # ← CSS injection
    ...
}
```

`bleach` was invoked without `css_sanitizer`, which it warns about at runtime:

```
NoCssSanitizerWarning: 'style' attribute specified, but css_sanitizer not set.
```

(Observed during this audit's testing.) Arbitrary CSS on a `<span>` permits
UI redressing — `position:fixed` overlays covering moderation controls,
content spoofing, and `background-image: url(//attacker/)` as a read receipt.
Not script execution in modern browsers.

`a: ['href']` without a `protocols` argument is **safe**: bleach's default
`ALLOWED_PROTOCOLS` is `['http', 'https', 'mailto']`, so `javascript:` URIs are
stripped. Verified by inspection of the bleach default.

Fix: pass a `bleach.css_sanitizer.CSSSanitizer` with an allowlist of properties,
or drop `style` from `ALLOWED_ATTRS`.

---

### SEC-20 — `RUNNER_SECRET` defaults to the empty string on the client side

**Severity:** Low · **Confirmed by inspection** · `config.py:38`, `app/challenge_runner.py:11`

```python
RUNNER_SECRET = os.environ.get('RUNNER_SECRET', '')
```

The runner itself uses `os.environ["RUNNER_SECRET"]` and crashes without it,
which is correct fail-fast behaviour. The **web** side silently accepts an empty
string and sends `X-Runner-Secret: ""` on every call. Every launch then fails
with a 403 that surfaces to players as a generic error, with no diagnostic
pointing at the real cause.

`scripts/generate_secrets.py` only fills a key if the line exists and is empty,
so a hand-edited `.env` that drops the line produces exactly this state.

Make the web side fail fast too.

---

### SEC-21 — WebAuthn RP configuration defaults to localhost and is undocumented

**Severity:** Low · **Confirmed by inspection** · `app/routes/passkey.py:21-24`

```python
RP_ID  = os.environ.get('PASSKEY_RP_ID', 'localhost')
ORIGIN = os.environ.get('PASSKEY_ORIGIN', 'http://localhost:5050')
```

Neither variable appears in `.env.template`, in the old README, or in any guide
under `docs/`. An operator following the documented setup deploys with
`RP_ID='localhost'`.

The failure is **closed**, not open — `assert client_data['origin'] == ORIGIN`
rejects every real assertion, so passkeys simply never work. But the error
surfaced to the user is the generic *"Authentication verification failed"*, with
nothing pointing at configuration. Both variables are now documented in the
README's configuration reference; they should also be added to `.env.template`
and validated at startup.

---

### SEC-22 — Base images and system packages are unpinned

**Severity:** Low · **Confirmed by inspection** · `Dockerfile`, `runner/Dockerfile`

`FROM python:3.11-slim`, `FROM docker:27-cli`, and the challenge images
(`php:8.2-cli-alpine`, `node:20-alpine`, `eclipse-temurin:21-jre-alpine`,
`python:3.11-alpine`, `debian:bookworm-slim`) are all floating tags with no
digest pin. `apt-get install` pins no versions, and `npm install -g ts-node
typescript` pins nothing.

Python dependencies **are** pinned exactly, which is the harder half — this is
the remaining gap. Combined with [DEV-15](development-audit.md) (nsjail from an
unpinned git clone), no two builds of this image are guaranteed identical.

---

### SEC-23 — Session cookie security depends on an environment variable

**Severity:** Low · **Confirmed by inspection** · `config.py:23-27`

```python
SESSION_COOKIE_SECURE  = os.environ.get('FLASK_ENV') != 'development'
REMEMBER_COOKIE_SECURE = os.environ.get('FLASK_ENV') != 'development'
```

This defaults to **secure** (any value other than `'development'`, including
unset, enables the flag), which is the right default and worth crediting.

The risk is operational: `docker-compose.dev.yml` sets
`FLASK_ENV=development`. Before this refactor that file was named
`docker-compose-override.yml` — one character away from
`docker-compose.override.yml`, which Compose auto-loads. Renaming it "to fix it"
would have silently stripped `Secure` from cookies in production.

It has been renamed to `docker-compose.dev.yml` so it can only ever be applied
explicitly with `-f`. Consider also logging a loud warning at startup when
`FLASK_ENV=development`.

`HttpOnly` and `SameSite=Lax` are set unconditionally. ✅

---

## 5. Controls that are working

Several defences here are done properly, and a list of findings without them
misrepresents the codebase.

| Control | Implementation | Assessment |
|---|---|---|
| **Path traversal defence** | `_safe_join` in `challenges.py:24`, `submissions.py:57`, `runner/main.py:190`; `_safe_filename` via `secure_filename(os.path.basename(...))` in `settings.py:21` | **Correct.** `os.path.basename` then `realpath` with a `startswith` containment assertion. Applied at every file-serving route without exception. |
| **SQL injection defence** | SQLAlchemy ORM throughout; 24 `text()` statements in `admin.py` all parameterised with `:u` / `:c` | **Correct.** No string interpolation reaches a query anywhere in the codebase. |
| **Tar extraction** | `_extract_archive`, `runner/main.py:200` | **Correct for traversal** — normalises, rejects `..`, re-checks resolved paths. See [SEC-15](#sec-15--copytree-on-extracted-archives-dereferences-symlinks) for the separate symlink issue in the unwrap step. |
| **Flag injection** | `_inject_flag`, `runner/main.py:221-237` | **Notably good.** Uses `os.fwalk` with `dir_fd` and `os.open(..., dir_fd=dirfd)` to avoid a TOCTOU race on the write. That is a level of care most projects do not reach. |
| **Password hashing** | Werkzeug 3.0 `generate_password_hash` (scrypt default) | **Correct.** Modern, memory-hard, salted. |
| **Runner authentication** | `secrets.compare_digest` on a shared header, bound to `127.0.0.1:32526` | **Correct.** Constant-time, and not reachable from outside the host. |
| **Session cookies** | `HttpOnly` + `SameSite=Lax` always; `Secure` unless `FLASK_ENV=development` | **Correct**, with the operational caveat in [SEC-23](#sec-23--session-cookie-security-depends-on-an-environment-variable). `HttpOnly` is what limits SEC-01 to same-origin action rather than session theft. |
| **Secret management** | `config.py` raises at import without `SECRET_KEY`; Dockerfile removes `.env` and certificates from the image | **Correct.** Fail-fast, no default key. |
| **Post sanitisation** | `bleach.clean` with a tag/attribute allowlist on `new_post` and `edit_post` | **Correct** for posts; the bug is that comments were not given the same treatment ([SEC-01](#sec-01--stored-xss-in-community-comments)). |
| **Ban enforcement** | `@app.before_request` hook checks `is_banned` on every request and force-logs-out | **Correct.** Enforced globally, not per-route. |
| **Passkey replay protection** | Signature counter comparison, `passkey.py:378-381` | **Correct** logic, undermined by [SEC-05](#sec-05--security-assertions-written-as-assert). |
| **Resource limits on instances** | 128 MB / 0.25 CPU / 64 pids per container | **Correct** for DoS; does nothing for isolation ([SEC-04](#sec-04--challenge-containers-run-as-root-with-full-network-access)). |
| **Dynamic per-user flags** | SHA-256 of 32 random bytes, injected per launch | **Correct** cryptographically; see the frontend leak noted in [`docs/roadmap.md`](../docs/roadmap.md). |

---

## 6. Summary

| ID | Finding | Severity | CWE | Status |
|---|---|---|---|---|
| SEC-01 | Stored XSS in community comments | **Critical** | 79 | Verified |
| SEC-02 | Live database in git history | **Critical** | 312, 540 | Verified |
| SEC-03 | Docker socket mounted into the runner | **Critical** | 250, 269 | Inspection |
| SEC-04 | Challenge containers root + bridged network | High | 250, 923 | Inspection |
| SEC-05 | Security checks written as `assert` | High | 617 | Inspection |
| SEC-06 | Containers run as root; oversized web image | High | 250 | Inspection |
| SEC-07 | 31 CSRF-exempt state-changing endpoints | High | 352 | Inspection |
| SEC-08 | No rate limiting anywhere | High | 307, 770 | Inspection |
| SEC-09 | CSV injection via unvalidated username change | High | 1236 | Verified |
| SEC-10 | ReDoS via author-supplied regex flags | Medium | 1333 | Inspection |
| SEC-11 | Passkey sudo coverage incomplete | Medium | 862 | Inspection |
| SEC-12 | Unbounded image upload storage | Medium | 770 | Inspection |
| SEC-13 | No password policy | Medium | 521 | Inspection |
| SEC-14 | Audit log trusts client IP headers | Medium | 348 | Inspection |
| SEC-15 | `copytree` dereferences symlinks on unwrap | Medium | 59 | Inspection |
| SEC-16 | Non-constant-time flag comparison | Low | 208 | Inspection |
| SEC-17 | Bug reports stored unvalidated | Low | 20 | Inspection |
| SEC-18 | Open-redirect gap on backslash in `next` | Low | 601 | Inspection |
| SEC-19 | `style` attribute permitted in sanitised HTML | Low | 79 | Inspection |
| SEC-20 | `RUNNER_SECRET` defaults to empty on the client | Low | 1188 | Inspection |
| SEC-21 | WebAuthn RP config defaults to localhost | Low | 1188 | Inspection |
| SEC-22 | Base images and packages unpinned | Low | 1104 | Inspection |
| SEC-23 | Cookie security depends on an env var | Low | 614 | Inspection |

### Overall assessment

**Do not expose this deployment publicly until SEC-01, SEC-02, SEC-03, SEC-07,
and SEC-08 are addressed.** SEC-01 and SEC-09 are verified working exploits
available to any registered user; SEC-02 has already happened and needs rotation
rather than a patch.

The encouraging half: the defensive controls that *are* present are present
because someone thought carefully about them. `os.fwalk` with `dir_fd` for flag
injection, `compare_digest` for the runner secret, `realpath` containment on
every file route, and a config that refuses to boot without a secret key are not
accidents. The gaps are consistency gaps — one sanitiser call missing from one
of two code paths, one validation regex applied at registration but not at
update, one set of hardening flags omitted from a `containers.run` call.

That is a much better position to be in than the finding count suggests,
because consistency gaps are cheap to close. Three of the five blocking issues
are under an hour of work each. See
[`remediation-plan.md`](remediation-plan.md).
