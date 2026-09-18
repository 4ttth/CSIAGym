# Audit documents

An independent review of the CSIA GYM codebase, carried out against commit
`fc67d61` on branch `claude/nice-gauss-u9nl2q`.

| Document | Contents |
|---|---|
| [`development-audit.md`](development-audit.md) | Code quality, architecture, correctness bugs, maintainability, tooling gaps. 24 findings. |
| [`security-audit.md`](security-audit.md) | Threat model, vulnerability findings with reproduction steps, defensive controls already in place. 23 findings. |
| [`remediation-plan.md`](remediation-plan.md) | Prioritised, sequenced fix plan with effort estimates, acceptance criteria, and code where it is short enough to inline. |

## How to read these

Findings carry a stable ID — `DEV-nn` for development, `SEC-nn` for security —
so they can be referenced from issues, commits, and the remediation plan. Each
one states **what**, **where** (file and line), **why it matters**, and
**how to confirm it**.

Every finding is marked with its verification status:

| Marker | Meaning |
|---|---|
| **Verified** | Reproduced against a running instance during this audit, or proved by direct inspection of the artifact (e.g. reading the blob out of git history). The evidence is quoted in the finding. |
| **Confirmed by inspection** | Established by reading the code. The control flow is unambiguous, but it was not executed. |
| **Assessed** | A judgement about design, risk, or maintainability rather than a defect with a reproduction. |

Severity uses the usual five-band scale. For security findings it reflects
exploitability **by a registered, non-privileged user** against a public
deployment, because that is this platform's actual threat: a CTF site invites
its own users to attack it.

## Scope

**In scope.** All application code (`app/`), the challenge-execution sidecar
(`runner/`), container and orchestration definitions, deployment assets, the
dependency manifest, and the repository's git history.

**Out of scope.** The security of individual CTF challenges (deliberately
vulnerable code is the product); the host OS and network perimeter; third-party
service configuration (Cloudflare, DNS, certificate issuance); and formal
penetration testing of a live deployment.

## What this audit is not

It is a static review plus targeted dynamic verification of specific findings
against a locally booted instance. It is not a penetration test, it does not
include fuzzing or dependency-chain analysis beyond version checks, and a clean
finding list here does not mean the platform is safe to expose unattended.

## Method

1. Read every Python module, Jinja template, and container definition in the repository.
2. Enumerated all 140 registered routes and traced authentication, authorization, and CSRF coverage for each.
3. Traced untrusted input from every entry point (forms, JSON bodies, uploads, tar archives, headers) to every sink (SQL, filesystem, HTML, `subprocess`/Docker, CSV).
4. Booted the application against a scratch SQLite database and exercised the flows behind the highest-severity findings to confirm or reject them.
5. Walked the git history for secrets and for the shape of the project's engineering practice.

## Headline result

The platform is **substantially more security-conscious than most projects of
its size**. Path traversal, tar extraction, SQL injection, password hashing,
session cookie flags, and the runner's authentication are all handled correctly
and deliberately — in several places more carefully than the framework requires.
Someone clearly thought about this.

The problems are concentrated in three places:

1. **One sanitisation gap** — community comments miss the `bleach.clean()` that posts get, and are rendered with `| safe`. That single inconsistency is a full stored-XSS ([SEC-01](security-audit.md)), verified working.
2. **Two structural decisions** — the Docker socket mounted into the runner, and challenge containers running as root on a bridged network ([SEC-03](security-audit.md), [SEC-04](security-audit.md)). Both are defensible shortcuts for a closed cohort and dangerous for a public deployment.
3. **Absent engineering scaffolding** — no tests, no CI, no linter, no migrations ([DEV-01](development-audit.md) onward). This is why defects like the category-vocabulary drift ([DEV-04](development-audit.md)) and the unreachable admin password ([DEV-02](development-audit.md)) survived to production.

Plus one historical accident that cannot be undone by editing code: the live
database sat in version control for most of the project's life
([SEC-02](security-audit.md)).

See [`remediation-plan.md`](remediation-plan.md) for what to do about all of it,
in order.
