# Archive

Material kept for provenance, **not** part of the running application. Nothing
here is imported by `app/`, copied into the Docker image (see `.dockerignore`),
or required to build or run the platform.

| Path | What it is | Why it is here |
|---|---|---|
| `legacy-runners/web_runner.py` | Subprocess-based web-challenge launcher | Superseded by the `runner/` sidecar; `app/challenge_runner.py` states it "replaces nc_runner.py and web_runner.py entirely". Verified unreferenced before moving. |
| `legacy-runners/nc_runner.py` | Subprocess/socat-based PWN-challenge launcher | Same as above. |
| `q-dev-chat-2026-03-21.md` | AI pair-programming transcript (330 KB) | Historical design discussion from development. |
| `q-dev-chat-2026-04-02.md` | AI pair-programming transcript (186 KB) | Historical design discussion from development. |

The legacy runners are retained because they document the pre-Docker execution
model (`unshare` + `setrlimit` sandboxing), which is still the reference for how
challenge isolation is *supposed* to behave. They are dead code: delete them
once the sidecar's isolation posture is settled — see
[`audit-docs/remediation-plan.md`](../audit-docs/remediation-plan.md).
