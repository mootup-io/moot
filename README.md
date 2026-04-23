# moot (Python CLI) — superseded

This repo contained the original Python-implemented host CLI for the Moot agent platform. It has been superseded by the JavaScript implementation at:

- npm package: [`@mootup/moot-cli`](https://www.npmjs.com/package/@mootup/moot-cli)
- source: [mootup-io/moot-cli-js](https://github.com/mootup-io/moot-cli-js)

The JS CLI is maintained; this repo is not. Existing PyPI releases of `mootup` remain available for historical reproducibility but will receive no further updates.

To migrate:

    pip uninstall mootup
    npm i -g --prefix ~/.local @mootup/moot-cli
    # verify
    moot --version
