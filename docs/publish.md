# Publishing `mootup` to PyPI

One-page runbook for cutting a new `mootup` release. Every new user who
runs `moot init` + `moot up` hits `pip install mootup` in the bundled
`post-create.sh`, so PyPI must stay current with tagged versions.

## Prerequisites

- PyPI account on <https://pypi.org> with upload rights on the `mootup`
  project.
- `twine` installed: `pip install twine` (or `uv tool install twine`).
- Credentials available to `twine` via either:
  - `~/.pypirc` with a `[pypi]` section containing an API token, or
  - environment: `TWINE_USERNAME=__token__` and
    `TWINE_PASSWORD=pypi-AgEI…` exported for the shell session.
- `build` installed: `pip install build` (skip if you use `uv build`).

## Version bump

Two authoritative sites; both must match.

- `src/moot/__init__.py` → `__version__ = "<new>"`
- `pyproject.toml` → `version = "<new>"`

Confirm no stray hard-coded version refs:

```bash
grep -rn '0\.2\.' src/ pyproject.toml
# allow list: __init__.py + pyproject.toml only
```

## Build

```bash
rm -rf dist/
python -m build         # or: uv build
```

Produces `dist/mootup-<new>-py3-none-any.whl` and
`dist/mootup-<new>.tar.gz`.

## Upload

```bash
twine upload dist/*
```

Twine prompts for credentials if `~/.pypirc` and `TWINE_*` are both
absent. On success it prints a URL like
`https://pypi.org/project/mootup/<new>/`.

## Post-publish smoke

Install from PyPI in a clean venv and confirm the version:

```bash
python -m venv /tmp/mootup-smoke
source /tmp/mootup-smoke/bin/activate
pip install 'mootup==<new>'
moot --version         # should print: moot <new>
deactivate
rm -rf /tmp/mootup-smoke
```

## Tag and push

```bash
git tag v<new>
git push origin v<new>
```

Optional but recommended — keeps the release history aligned with
PyPI. If the tag is pushed before `twine upload` and the upload fails,
delete with `git push origin :refs/tags/v<new>` and retry.

## Troubleshooting

- **`HTTPError: 403 Forbidden` on upload.** Token is missing upload
  rights on the `mootup` project, or scoped to a different project.
  Generate a new project-scoped token on PyPI.
- **`File already exists` on upload.** PyPI does not allow re-uploading
  the same version. Bump the version and rebuild.
- **`mootup <new>` not found from `pip install`.** PyPI CDN can lag by
  up to a minute after upload. Retry, or pass `--no-cache-dir`.
