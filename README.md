# moot (Python CLI) — superseded

> **Status: Legacy / mirror-only.** This Python `moot` CLI is retained for security-mirror parity with `mootup-io/moot-cli-js` (the active JS host CLI). For new operator workflows, use **`mootup-io/moot-cli-js`** instead — `npm install -g @mootup/moot-cli`. The `moot init --fresh` flag (and its phantom `/api/tenants/{tenant_id}/agents` route call, ARCH-1 F11.1) is deprecated; provisioning operator workflows route through the JS CLI. ARCH-7 F-ARCH-7-PYTHON-CLI-RETIRED tracks finalization.

This repo contained the original Python-implemented host CLI for the Moot agent platform. It has been superseded by the JavaScript implementation at:

- npm package: [`@mootup/moot-cli`](https://www.npmjs.com/package/@mootup/moot-cli)
- source: [mootup-io/moot-cli-js](https://github.com/mootup-io/moot-cli-js)

The JS CLI is maintained; this repo is not. Existing PyPI releases of `mootup` remain available for historical reproducibility but will receive no further updates.

To migrate:

    pip uninstall mootup
    npm i -g --prefix ~/.local @mootup/moot-cli
    # verify
    moot --version
