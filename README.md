# moot (Python) — retired as a *host* CLI; live as the *in-container* runtime

> **Status: the host CLI is superseded. The in-container runtime is not — it is
> load-bearing and maintained.**
>
> Read that split carefully before believing anything else here, because this
> file previously said "this repo is not maintained" full stop, and that was
> wrong in a way that cost real time: the `mootup` pip package is what launches
> and manages every agent in a devcontainer team. A codex-harness bug sat
> unfixed in `launch.py` partly because the file carrying it was labelled
> untouchable.

**Two things live in this repo, with opposite lifecycles:**

| Surface | Status | Who uses it |
|---|---|---|
| **In-container runtime** — `launch.py`, `lifecycle.py`, `devcontainer.py`, `adapters/` | **Live and maintained.** Reads `moot.toml`, creates worktrees, drives tmux, launches agents. | Every devcontainer team. Installed by `pip install mootup` in a project's `post-create.sh`; `moot up` on the host shims into `docker exec <cid> moot up`, and *this* is the side that does the work. |
| **Host CLI** — `moot init`, `moot login`, provisioning, scaffolding | **Superseded.** Use [`@mootup/moot-cli`](https://www.npmjs.com/package/@mootup/moot-cli) (`npm install -g @mootup/moot-cli`), source at [mootup-io/moot-cli-js](https://github.com/mootup-io/moot-cli-js). | Operators setting up a new project. |

`moot init --fresh` (and its phantom `/api/tenants/{tenant_id}/agents` route
call, ARCH-1 F11.1) is deprecated; provisioning routes through the JS CLI.
ARCH-7 F-ARCH-7-PYTHON-CLI-RETIRED tracks finalization **of the host-CLI half
only** — it does not retire the runtime.

Changes to the in-container runtime ship as normal PyPI releases: bump
`pyproject.toml`, refresh `uv.lock`, tag `v*.*.*`, and the publish workflow
does the rest. A project's `post-create.sh` picks the new version up on its
next rebuild, so an unreleased fix is an unapplied fix no matter how well it
works locally.

**Harness support note.** The JS CLI owns harness selection at `init` time
(`claude-code`, `codex`, `cursor-agent`, `cursor-ide`, `sdk`) and ships the
matching devcontainer templates. This package's own `moot init` predates that
and hardcodes `claude-code`; it is part of the superseded half. The *runtime*
here is harness-aware and must stay so — see `_BYPASS_PERMISSION_MODES` and
`_seed_codex_trust` in `launch.py`.

To migrate:

    pip uninstall mootup
    npm i -g --prefix ~/.local @mootup/moot-cli
    # verify
    moot --version
