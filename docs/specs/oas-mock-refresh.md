# oas-mock-refresh

**Status:** Design spec
**Author:** Spec
**Run:** X (2026-04-18)
**Repo:** `mootup-io/moot`
**Feat branch:** `feat/oas-mock-refresh` from `main` @ `1546cf9`
**OAS source:** `/workspaces/convo/docs/api/openapi.yaml` (convo Run W, commit `b6f6d13` — OpenAPI 3.1.0)

## 1. Summary

Two intertwined hygiene passes in one run:

1. **Refresh stale `respx` mocks** in `mootup-io/moot/tests/` so endpoint paths, request params, and response bodies match the current convo backend. The scaffold flow has silently drifted to a new endpoint (`GET /api/actors/me/agents`) that none of the mocks stub — all 9 `test_scaffold` tests fail with `AllMockedAssertionError`. Anchor per endpoint: OAS for path/method/params (authoritative), backend route handlers and Pydantic models (authoritative for response body — OAS emits `additionalProperties: true` so it does not constrain body shape).
2. **Retire dead tests** that have been failing since the alpha bring-up: `test_example.py` (6 tests tracking a non-existent `examples/markdraft/` directory) and `test_templates.py::test_publish_doc_exists` (tests a non-existent `docs/publish.md`).

Mechanical-lift pipeline. No semantic design decisions. Three D-decisions documented in § 4, all resolved in-draft.

## 2. Baseline (cross-repo first run — remeasured at feat-tip)

BASELINE-FROZEN @ `1546cf9` in `/workspaces/convo/mootup-io/moot/.worktrees/spec/`:

```
$ .venv/bin/python -m pytest
124 tests collected
15 failed, 109 passed in 3.17s

Failures:
  tests/test_example.py::test_moot_toml_valid              (examples/markdraft/ missing)
  tests/test_example.py::test_devcontainer_json_valid      (examples/markdraft/ missing)
  tests/test_example.py::test_post_create_installs_moot    (examples/markdraft/ missing)
  tests/test_example.py::test_runner_scripts_unchanged     (examples/markdraft/ missing)
  tests/test_example.py::test_gitignore_entries            (examples/markdraft/ missing)
  tests/test_scaffold.py::test_init_greenfield_rotates_and_installs
  tests/test_scaffold.py::test_init_conflict_stages_claude_md
  tests/test_scaffold.py::test_init_conflict_stages_skill
  tests/test_scaffold.py::test_init_conflict_stages_devcontainer
  tests/test_scaffold.py::test_init_force_rotates_keys
  tests/test_scaffold.py::test_init_adopt_fresh_install_overwrites
  tests/test_scaffold.py::test_init_rotate_key_failure_does_not_persist
  tests/test_scaffold.py::test_init_warns_on_non_git_repo
  tests/test_scaffold.py::test_init_placeholder_substitution
  tests/test_templates.py::test_publish_doc_exists         (docs/publish.md missing)
```

```
$ .venv/bin/python -m pyright
12 errors, 0 warnings, 0 informations
  src/moot/adapters/mcp_adapter.py   (11 errors — pre-existing, out of scope)
  tests/test_launch.py                (1 error  — pre-existing, out of scope)
```

**No pytest-xdist** in moot-cli (`pyproject.toml` test deps: `pytest>=8.0`, `pytest-asyncio>=0.24`, `respx>=0.22`). All test commands in this spec use plain `pytest` — do NOT add `-n auto`.

**Pre-existing pyright errors (12) are out of scope.** This run touches only `tests/test_scaffold.py`, `tests/test_example.py`, `tests/test_templates.py`. Ship gate is "no NEW pyright errors introduced" — baseline total may remain at 12.

## 3. Scope

**In:**
- Refresh respx mock bodies in `tests/test_scaffold.py` so endpoint paths match the current scaffold flow and response bodies match `Actor.model_dump()` / `SpaceInfo.model_dump()` shape.
- Refresh respx mock bodies in `tests/test_provision.py` and `tests/test_auth.py` so response bodies match the backend's actual model_dump() shape (currently passing but author-imagined minimal dicts).
- Delete `tests/test_example.py` in full (6 tests against non-existent `examples/markdraft/`).
- Delete `tests/test_templates.py::test_publish_doc_exists` (single test against non-existent `docs/publish.md`).

**Out:**
- Generating a typed Python client from the OAS (separate task, not this run).
- Backend (convo) changes. OAS is the emitted contract; it is read-only here.
- Adding new test coverage beyond refresh + deletion.
- Fixing pre-existing pyright errors in `mcp_adapter.py` / `test_launch.py`.
- Deleting dead CLI commands (`cmd_provision`, cosmetic fallback in scaffold.py) — see § 11 findings.
- Restoring `examples/markdraft/` or `docs/publish.md` (deferred; if either ships later, add new tests against the real tree then).

## 4. Decisions (resolved in-draft)

### D1 — Response-body anchor when OAS does not constrain shape

The convo OAS declares almost every successful response body as `additionalProperties: true, type: object` (or `list[...dict]`). FastAPI routes emit `dict = model.model_dump()` without a `response_model=` declaration, so the OAS reflects "any object." Validating mock bodies against the OAS therefore admits any dict — useless as a drift gate on shape.

**Resolution:** OAS is authoritative for **endpoint path, method, path params, query params, and request body** (where `$ref` schemas exist). **Response body shape** is anchored to the backend Pydantic model that each route handler's `model_dump()` call exposes (`Actor`, `SpaceInfo`, etc.) — Spec enumerates the required fields per mock in § 6.1. This matches `feedback_cross_repo_http_mocks_via_oas` ("grep the route handler for its return type and copy fields exactly"). Revisit once convo routes gain `response_model=` declarations (out of scope here).

### D2 — `test_example.py` triage: delete the whole file

Every test in `test_example.py` reads from `EXAMPLE_DIR = Path(__file__).parent.parent.parent / "examples" / "markdraft"`. The `examples/` directory does not exist at `feat/oas-mock-refresh` tip and is not tracked in git (`git ls-files examples/` empty). Five tests fail with `FileNotFoundError`; one (`test_no_convo_specific_paths`) passes vacuously because `rglob("*")` over a missing directory yields nothing.

**Options:**
- (a) Delete the whole file.
- (b) Skip all tests with `@pytest.mark.skip(reason="examples/markdraft/ not yet restored")`.
- (c) Recreate `examples/markdraft/`. Out of scope (Product-direction, not test hygiene).

**Resolution: (a) delete the file.** The tests describe a fixture tree that has been absent for the entire alpha-stabilization window. If examples are ever restored, their shape will differ and the tests would need to be rewritten anyway — skip-markers would be dead scaffolding.

### D3 — `test_publish_doc_exists` triage: delete the single test

`tests/test_templates.py::test_publish_doc_exists` asserts `docs/publish.md` exists in the moot repo. Neither the file nor the `docs/` directory exists (`git ls-files docs/` empty). The publish procedure the test was guarding has not landed in-tree.

**Resolution:** delete the single test body from `test_templates.py`. Keep the other 17 tests in that file (all passing). If publish docs land later, add a fresh test pinned to whatever is actually shipped.

## 5. Endpoint catalogue (what each mock currently asserts vs what the backend emits)

Authoritative refs: `backend/core/models/models.py` (Actor, SpaceInfo), `backend/api/routes/actors.py`, `backend/api/routes/spaces.py`, `/workspaces/convo/docs/api/openapi.yaml`.

### 5.1 `GET /api/actors/me` — returns `Actor.model_dump()`

**Fields** (all present in the dump):

| field | type | notes |
|---|---|---|
| `actor_id` | `str` | encoded `agt_*` / `usr_*` |
| `display_name` | `str` | |
| `actor_type` | `str` | `"human"` \| `"agent"` |
| `sponsor_id` | `str \| None` | |
| `tenant_id` | `str \| None` | FK |
| `is_admin` | `bool` | default False |
| `email` | `str \| None` | |
| `agent_profile` | `str \| None` | |
| `api_key_prefix` | `str \| None` | first 8 chars of live key, None if keyless |
| `default_space_id` | `str \| None` | encoded `spc_*` |
| `is_connected` | `bool \| None` | agent-only; None for humans |
| `focus_space_id` | `str \| None` | |
| `metadata` | `dict \| None` | |
| `last_seen_at` | `str \| None` | ISO-8601 |
| `created_at` | `str` | ISO-8601, required |
| `updated_at` | `str` | ISO-8601, required |

**Consumer reads in moot-cli:**
- `scaffold.py:176` — `actor.get("default_space_id")` (uses)
- `provision.py:49` — `me.get("tenant_id")` (uses)
- `auth.py` — cmd_login uses only the presence of 200 (no field reads)

### 5.2 `GET /api/spaces/{space_id}` — NOT IMPLEMENTED

OAS has `patch:` but NO `get:` on this path (`api/routes/spaces.py` line 155 is the patch; no GET). `scaffold.py:181` issues a GET and silently swallows the 404/405 via `space_resp.status_code == 200` guard, falling back to `space_name = space_id`. See § 11.F1 for disposition.

**Mock disposition:** stub a **404** response (matches production behavior); remove the bogus `{"name": "Test Space"}` body. This keeps the fallback path exercised by tests.

### 5.3 `GET /api/spaces/{space_id}/participants` — NO LONGER CALLED BY SCAFFOLD

`scaffold.py` replaced this endpoint with `/api/actors/me/agents` (see docstring of `_fetch_keyless_agents` at scaffold.py:190–214, which narrates the switch). The endpoint is still live on the backend (`api/routes/spaces.py:...`) but moot-cli no longer calls it in the init flow.

**Mock disposition:** DELETE the `/api/spaces/{space_id}/participants` mock stub from `_stub_backend` (and from every per-test inline stub). Because `@respx.mock` defaults to `assert_all_called=True`, leaving an unused mock would flip every test from `AllMockedAssertionError` to `AllCalledAssertionError`.

### 5.4 `GET /api/actors/me/agents` — NEW (returns `list[Actor.model_dump()]`)

Route: `api/routes/actors.py:217–225`.
```python
@router.get("/api/actors/me/agents")
async def get_my_agents(actor: Actor = Depends(require_actor)) -> list[dict]:
    if actor.actor_type != "human":
        raise HTTPException(status_code=403, ...)
    ...
    return [a.model_dump() for a in agents]
```

Returns **all agents sponsored by the caller**, regardless of space. Each dict carries the full Actor shape (§ 5.1).

**Consumer reads in moot-cli** (`scaffold.py:215–225`):
- `a.get("actor_type") == "agent"` — filters to agents
- `a.get("api_key_prefix")` — filters to keyless when `force=False`
- `a["actor_id"]` — used in rotate-key URL
- `a["display_name"]` — used for role key

**Mock disposition:** ADD a `/api/actors/me/agents` stub to `_stub_backend` returning 4 Actor dicts (one per role), each with `actor_type="agent"` and `api_key_prefix=None` (so the keyless filter admits all 4). Other Actor fields set to representative values.

### 5.5 `POST /api/actors/{actor_id}/rotate-key` — returns `Actor.model_dump()` + `{"api_key": ...}`

Route: `api/routes/actors.py:397–401`.
```python
refreshed = await actor_store.get_actor(pool, actor_id)
result = refreshed.model_dump() if refreshed else target.model_dump()
result["api_key"] = new_key
return result
```

**Consumer reads in moot-cli** (`scaffold.py:250–255`): `data.get("api_key", "")` only. The other Actor fields are emitted but unused by moot-cli.

**Mock disposition:** response body must include `api_key` + full Actor shape. Current mocks emit `{"api_key": "convo_key_live_{role}"}` only — thin but functionally sufficient. Per D1, expand to full Actor + api_key so the test documents the real shape.

### 5.6 `POST /api/tenants/{tenant_id}/agents` — PHANTOM (not in OAS; not in routes/)

Called by `provision.py:56–62`. Does not exist on the backend (OAS grep for `/api/tenants/` shows only `POST /api/tenants`, `GET /api/tenants/{tenant_id}`, and admin variants — no `/{tenant_id}/agents`). In production this request would 404.

`test_provision.py::test_provision_fresh_writes_moot_agents_fresh_json` mocks the phantom endpoint with `{"actor_id": "agt_p", "api_key": "convo_key_fresh"}` and self-confirms. See § 11.F2 for disposition.

**Mock disposition:** keep the existing phantom mock as-is (Product-direction call; see § 11.F2). Add a code comment in the test file citing this spec so the phantom is visible.

## 6. Files to modify

| # | File | Action | Scope |
|---|------|--------|-------|
| 1 | `tests/test_example.py` | **delete** | removes 6 tests (5 failing + 1 vacuous) |
| 2 | `tests/test_templates.py` | edit | delete the 22-line `test_publish_doc_exists` body (1 test) |
| 3 | `tests/test_scaffold.py` | edit | rewrite `_stub_backend` helper, update 2 inline stubs in `test_init_rotate_key_failure_does_not_persist`, adjust one assertion that indexes `respx.mock.routes[3]` |
| 4 | `tests/test_provision.py` | edit | expand the `/api/actors/me` mock body to match `Actor` shape; add comment annotating the phantom `/api/tenants/.../agents` endpoint |
| 5 | `tests/test_auth.py` | edit | expand the 2 `/api/actors/me` mocks to match `Actor` shape |

No source code (`src/moot/*.py`) changes. No new files. No pyproject/lockfile changes.

## 6.1 Canonical Actor mock dict (paste-ready)

Use this dict (fill `actor_id`, `display_name`, `actor_type`, `sponsor_id`, `api_key_prefix`, `default_space_id` per call site) as the common body shape for every Actor-returning mock in this run. All other fields use these defaults:

```python
def _actor_dict(
    *,
    actor_id: str,
    display_name: str,
    actor_type: str = "agent",
    sponsor_id: str | None = "usr_test_1",
    api_key_prefix: str | None = None,
    default_space_id: str | None = None,
    is_connected: bool | None = False,
) -> dict:
    """Return a full Actor.model_dump() shape for respx mocks.

    Field order and defaults match backend/core/models/models.py::Actor.
    Only the fields callers vary are parameters; the rest are fixed
    canonical defaults so every mock emits a shape indistinguishable
    from a real backend response.
    """
    return {
        "actor_id": actor_id,
        "display_name": display_name,
        "actor_type": actor_type,
        "sponsor_id": sponsor_id,
        "tenant_id": "ten_test_1",
        "is_admin": False,
        "email": None,
        "agent_profile": None,
        "api_key_prefix": api_key_prefix,
        "default_space_id": default_space_id,
        "is_connected": is_connected,
        "focus_space_id": None,
        "metadata": None,
        "last_seen_at": None,
        "created_at": "2026-04-18T00:00:00+00:00",
        "updated_at": "2026-04-18T00:00:00+00:00",
    }
```

Place at the top of `tests/test_scaffold.py` after imports (before `_stub_backend`). **Do NOT also place it in `test_provision.py` or `test_auth.py`** — their Actor shapes are simple enough to inline; duplicating the helper adds no value.

## 7. § 6.1 — test_scaffold.py canonical rewrite

### 7.1 Rewrite `_stub_backend`

Replace lines 17–56 of `tests/test_scaffold.py` with:

```python
def _stub_backend(respx_mock: respx.Router, api_url: str) -> None:
    """Stub the 3-call happy-path flow (post-Run-W scaffold).

    Endpoints (all anchored to convo OAS b6f6d13):
      GET  /api/actors/me                   — Actor.model_dump()
      GET  /api/spaces/{space_id}           — 404 (no GET handler; scaffold falls back to space_id)
      GET  /api/actors/me/agents            — list[Actor.model_dump()]
      POST /api/actors/{actor_id}/rotate-key — Actor.model_dump() + api_key
    """
    respx_mock.get(f"{api_url}/api/actors/me").mock(
        return_value=Response(
            200,
            json=_actor_dict(
                actor_id="usr_user_1",
                display_name="Test User",
                actor_type="human",
                sponsor_id=None,
                default_space_id="spc_test_1",
            ),
        )
    )
    # GET /api/spaces/{id} is not implemented; scaffold swallows the 404.
    respx_mock.get(f"{api_url}/api/spaces/spc_test_1").mock(
        return_value=Response(404, json={"detail": "Not found"})
    )
    respx_mock.get(f"{api_url}/api/actors/me/agents").mock(
        return_value=Response(
            200,
            json=[
                _actor_dict(
                    actor_id=f"agt_{role.lower()}_1",
                    display_name=role,
                )
                for role in ("Product", "Spec", "Implementation", "QA")
            ],
        )
    )
    for role in ("product", "spec", "implementation", "qa"):
        respx_mock.post(
            f"{api_url}/api/actors/agt_{role}_1/rotate-key"
        ).mock(
            return_value=Response(
                200,
                json={
                    **_actor_dict(
                        actor_id=f"agt_{role}_1",
                        display_name=role.capitalize(),
                        api_key_prefix="convo_ke",
                    ),
                    "api_key": f"convo_key_live_{role}",
                },
            )
        )
```

### 7.2 `respx.mock.routes[3]` assertion in `test_init_force_rotates_keys`

Current line 263:
```python
rotate_call = respx.mock.routes[3].calls.last
```

The new `_stub_backend` registers routes in a different order: `/api/actors/me` (0), `/api/spaces/spc_test_1` (1), `/api/actors/me/agents` (2), `/api/actors/agt_product_1/rotate-key` (3), `.../agt_spec_1/rotate-key` (4), `.../agt_implementation_1/rotate-key` (5), `.../agt_qa_1/rotate-key` (6). Index 3 is still the first rotate-key — assertion semantics are preserved. **No change needed**.

### 7.3 `test_init_rotate_key_failure_does_not_persist` inline stubs

Lines 361–391 (inline stubs duplicating `_stub_backend`'s first 3 calls + a 500 on rotate-key for product only). Replace the 3 inline non-failure stubs with:

```python
respx.mock.get(f"{api_url}/api/actors/me").mock(
    return_value=Response(
        200,
        json=_actor_dict(
            actor_id="usr_user_1",
            display_name="Test User",
            actor_type="human",
            sponsor_id=None,
            default_space_id="spc_test_1",
        ),
    )
)
respx.mock.get(f"{api_url}/api/spaces/spc_test_1").mock(
    return_value=Response(404, json={"detail": "Not found"})
)
respx.mock.get(f"{api_url}/api/actors/me/agents").mock(
    return_value=Response(
        200,
        json=[
            _actor_dict(
                actor_id="agt_product_1",
                display_name="Product",
            )
        ],
    )
)
```

Keep the existing `respx.mock.post(f"{api_url}/api/actors/agt_product_1/rotate-key").mock(return_value=Response(500, json={"error": "boom"}))` line unchanged.

### 7.4 Import line

Top of `tests/test_scaffold.py` is already:
```python
import respx
from httpx import Response
```
No new imports needed.

## 8. § 6.2 — test_provision.py mock expansion

Update lines 54–63 to emit a full Actor shape for `/api/actors/me` (so the test documents the real shape) and add a comment pointing at the phantom endpoint:

```python
respx.mock.get("https://mootup.io/api/actors/me").mock(
    return_value=Response(
        200,
        json={
            "actor_id": "agt_u",
            "display_name": "Test User",
            "actor_type": "human",
            "sponsor_id": None,
            "tenant_id": "ten_1",
            "is_admin": False,
            "email": None,
            "agent_profile": None,
            "api_key_prefix": None,
            "default_space_id": None,
            "is_connected": None,
            "focus_space_id": None,
            "metadata": None,
            "last_seen_at": None,
            "created_at": "2026-04-18T00:00:00+00:00",
            "updated_at": "2026-04-18T00:00:00+00:00",
        },
    )
)
# NOTE: POST /api/tenants/{tenant_id}/agents is not implemented on the
# convo backend at b6f6d13 (no matching route; not in openapi.yaml).
# See docs/specs/oas-mock-refresh.md § 11.F2 — disposition deferred to
# Product (task #53 follow-up).
respx.mock.post("https://mootup.io/api/tenants/ten_1/agents").mock(
    return_value=Response(
        201, json={"actor_id": "agt_p", "api_key": "convo_key_fresh"}
    )
)
```

## 9. § 6.3 — test_auth.py mock expansion

Update lines 105–109 and 137–141 (two near-identical blocks). Current shape:
```python
mock.get("/api/actors/me").respond(
    200,
    json={"actor_id": "usr_test", "display_name": "Test User"},
)
```

Replace each with:
```python
mock.get("/api/actors/me").respond(
    200,
    json={
        "actor_id": "usr_test",        # or "usr_bypass" in the second block
        "display_name": "Test User",   # or "Bypass User"
        "actor_type": "human",
        "sponsor_id": None,
        "tenant_id": "ten_test_1",
        "is_admin": False,
        "email": None,
        "agent_profile": None,
        "api_key_prefix": None,
        "default_space_id": None,
        "is_connected": None,
        "focus_space_id": None,
        "metadata": None,
        "last_seen_at": None,
        "created_at": "2026-04-18T00:00:00+00:00",
        "updated_at": "2026-04-18T00:00:00+00:00",
    },
)
```

`cmd_login` only reads status 200 (see `auth.py:81–end`), so the additional fields are documentation, not behavior — but they keep the mocks honest to the real response shape.

## 10. § 7 — test_example.py deletion

`git rm tests/test_example.py`. No other references to this file in the tree (grep confirmed: the only occurrences are inside the file itself).

## 11. § 8 — test_templates.py single-test deletion

In `tests/test_templates.py`, delete the test function `test_publish_doc_exists` (one `def test_publish_doc_exists` block, 22 lines including its docstring referring to "Product scope item 4 (Run V)"). Leave every other test in the file untouched.

## 12. Pytest count formula

Baseline: 124 collected, 15 failed, 109 passed.

| Change | count |
|---|---|
| drops | −6 (test_example.py) − 1 (test_publish_doc_exists) = **−7** |
| rewrites | 0 (test_scaffold bodies rewritten in-place; no new `def test_*` lines) |
| adds | 0 |
| net | **−7** |

**Projected final:** 117 collected, 0 failed, 117 passed.

Breakdown of failures-to-green:
- 5 test_example failures → deleted
- 1 test_publish_doc_exists failure → deleted
- 9 test_scaffold failures → pass (mock refresh)
- Remainder: 109 pre-existing pass + 9 scaffold back in green = 117 passing.

## 13. Incremental plan for Impl (three stages, each independently green)

### Stage 1 — delete dead tests

1. `git rm tests/test_example.py`.
2. Delete `test_publish_doc_exists` from `tests/test_templates.py`.
3. `.venv/bin/python -m pytest` → **117 collected, 9 failed, 108 passed.** (Only scaffold failures remain; example+templates failures gone.)

### Stage 2 — test_scaffold.py mock refresh

1. Add `_actor_dict` helper at the top of `tests/test_scaffold.py` (§ 6.1).
2. Replace `_stub_backend` body (§ 7.1).
3. Update inline stubs in `test_init_rotate_key_failure_does_not_persist` (§ 7.3).
4. No change to `respx.mock.routes[3]` assertion (verify § 7.2 analysis).
5. `.venv/bin/python -m pytest tests/test_scaffold.py` → **13 passed** (9 refreshed + 4 pre-existing passers: `test_init_refuses_without_force_when_actors_exist`, `test_init_update_suggestions_no_network`, `test_infer_team_template`, `test_launch_includes_channel_flag`).

### Stage 3 — test_provision.py + test_auth.py shape expansion

1. Expand the `/api/actors/me` mock in test_provision.py (§ 8) and add the phantom-endpoint comment.
2. Expand the two `/api/actors/me` mocks in test_auth.py (§ 9).
3. `.venv/bin/python -m pytest` → **117 collected, 0 failed, 117 passed.**
4. `.venv/bin/python -m pyright` → **≤ 12 errors** (same files as baseline: `mcp_adapter.py` + `test_launch.py`; no new errors in the test files touched).

Each stage is a single commit so Leader can bisect if anything regresses.

## 14. Surprises for Impl

### Missing-imports audit

Every symbol referenced in § 6/§ 7/§ 8/§ 9 code blocks is already imported in the target files. Confirmed:
- `test_scaffold.py` imports: `respx`, `Response`, `pytest`, `json`, `os`, `stat`, `Path`, `cmd_init`, `ACTORS_JSON`. New `_actor_dict` uses only `dict` (builtin). No new imports needed.
- `test_provision.py` imports: `respx`, `Response`, `pytest`, `asyncio`, `json`, `Path`. No new imports needed.
- `test_auth.py` imports: already has `respx` (verified at line 105, 137). No new imports needed.

### Findings (out of scope; report to Product after ship)

**F1. `GET /api/spaces/{space_id}` is not implemented on the backend.** `scaffold.py:181` calls it and swallows the 404; `space_name` falls back to `space_id`. In production the user sees the space ID as the space name. Disposition options: (a) add the GET handler in backend (convo repo change); (b) remove the cosmetic call from moot-cli; (c) ship as-is. Not in this run's scope. Flag for Product at retro.

**F2. `POST /api/tenants/{tenant_id}/agents` is a phantom endpoint.** `provision.py:56` calls it; the OAS does not list it (grep `/api/tenants/` in openapi.yaml returns only `POST /api/tenants`, `GET /api/tenants/{tenant_id}`, and admin variants). `cmd_provision` would 404 in production. Disposition options: (a) delete `cmd_provision` and `test_provision.py` entirely; (b) add the route in backend; (c) ship as-is. The current run ships the code comment annotation (see § 8) so the phantom is visible to future readers. Design decision deferred to Product.

**F3. `@respx.mock` defaults to `assert_all_called=True` AND `assert_all_mocked=True`.** The § 7.1 `_stub_backend` rewrite DELETES the old `/api/spaces/{id}/participants` mock (no longer called) and ADDS the `/api/actors/me/agents` mock (now called). Leaving either one wrong flips every test. If Impl sees a new `AllCalledAssertionError` after stage 2, an old mock was retained; if `AllMockedAssertionError`, a new endpoint is missing. Both surface in a single green test run once § 7.1 is applied verbatim.

### Pyright on the rewritten test bodies

Dry-ran the embedded helper + mock snippets against `basic` mode pythonVersion 3.11. No `object`-typed captures, no `list[dict[str, object]]` subscript reads, no `monkeypatch.setattr` on paths that do not resolve. Clean.

### No xdist

`pyproject.toml` does not depend on `pytest-xdist`. Use plain `pytest` / `.venv/bin/python -m pytest`. Do not add `-n auto`.

### Cross-repo source of truth

OAS path at `/workspaces/convo/docs/api/openapi.yaml` is read-only from the moot worktree. Impl should `cat` or `grep` it for reference during implementation; do NOT copy it into the moot repo. The Actor / SpaceInfo models at `/workspaces/convo/backend/core/models/models.py` (lines 28–44 for Actor, 101–107 for SpaceInfo) are the canonical response-body reference.

## 15. QA spot-checks (§ 12)

**Q-1** — `git log -1 --stat` shows three commits, one per stage; no unrelated files touched.

**Q-2** — `git diff main -- src/` is empty (source code untouched).

**Q-3** — `git ls-files tests/test_example.py` returns empty; the file is gone.

**Q-4** — `grep -n '/api/spaces/{.*}/participants' tests/` is empty (the stale stub path is gone from all test files).

**Q-5** — `grep -n '/api/actors/me/agents' tests/test_scaffold.py` returns ≥ 1 hit (the new endpoint is present).

**Q-6** — `.venv/bin/python -m pytest` shows exactly `117 passed` (or whatever number matches § 12 net after the deletions; projected 117).

**Q-7** — `.venv/bin/python -m pyright` shows ≤ 12 errors, all in `mcp_adapter.py` (11) + `test_launch.py` (1). Zero new errors in the 4 touched test files.

**Q-8** — `test_init_force_rotates_keys` passes (validates § 7.2 index-3 assertion still points to the first rotate-key call).

**Q-9** — `grep -n "phantom" tests/test_provision.py` returns ≥ 1 hit (the F2-annotated comment landed in the file).

**Q-10** — Spot-read `tests/test_scaffold.py` and confirm `_actor_dict` appears exactly once (helper is not duplicated in per-test bodies).

## 16. § 13 — Verbatim grounding commands and output

Run in `/workspaces/convo/mootup-io/moot/.worktrees/spec/` at `1546cf9`.

### Phase A — confirm missing directories

```
$ git ls-files examples/        →  (empty)
$ git ls-files docs/            →  (empty)
$ ls examples/                  →  ls: cannot access 'examples/': No such file or directory
$ ls docs/                      →  ls: cannot access 'docs/': No such file or directory
```

### Phase B — enumerate respx mocks in moot-cli tests

```
$ grep -rln 'respx\.' tests/
tests/test_auth.py
tests/test_provision.py
tests/test_scaffold.py
```
Three files, exactly the five edit-targets in § 6 (file #1 is a deletion; files #2/#3/#4/#5 match).

### Phase C — endpoint catalogue in src/moot/

```
$ grep -rn '"/api/[^"]*"\|f"/api/[^"]*"' src/moot/ | grep -v adapters/
src/moot/auth.py:81:        resp = await client.get("/api/actors/me")
src/moot/provision.py:44:        me_resp = await client.get("/api/actors/me")
src/moot/provision.py:57:                f"/api/tenants/{tenant_id}/agents",
src/moot/scaffold.py:168:    resp = await client.get("/api/actors/me")
src/moot/scaffold.py:181:    space_resp = await client.get(f"/api/spaces/{space_id}")
src/moot/scaffold.py:215:    resp = await client.get("/api/actors/me/agents")
src/moot/scaffold.py:241:            f"/api/actors/{actor_id}/rotate-key",
```
7 call sites across scaffold.py / provision.py / auth.py — matches § 5.1–§ 5.6 cataloguing.

### Phase D — confirm phantom endpoints

```
$ grep -n '/api/spaces/{space_id}:' /workspaces/convo/docs/api/openapi.yaml
125:  /api/spaces/{space_id}:
$ sed -n '125,130p' /workspaces/convo/docs/api/openapi.yaml
  /api/spaces/{space_id}:
    patch:
      summary: Update Space
      ...
$ grep -n '/api/tenants/{tenant_id}/agents' /workspaces/convo/docs/api/openapi.yaml
(empty)
```
Confirms F1 (only PATCH on `/api/spaces/{id}`) and F2 (`/api/tenants/{id}/agents` not in OAS).

### Phase E — confirm route handlers for called endpoints

```
$ grep -n '@router.get("/api/actors/me"\|@router.get("/api/actors/me/agents"\|@router.post("/api/actors/{actor_id}/rotate-key"' \
      /workspaces/convo/backend/api/routes/actors.py
169:@router.get("/api/actors/me")
217:@router.get("/api/actors/me/agents")
358:@router.post("/api/actors/{actor_id}/rotate-key")
```
All three canonical endpoints exist on the backend.

### Phase F — Actor model field enumeration

`/workspaces/convo/backend/core/models/models.py:28–44`:
```
class Actor(BaseModel):
    actor_id: str
    display_name: str
    actor_type: str
    sponsor_id: str | None = None
    tenant_id: str | None = None
    is_admin: bool = False
    email: str | None = None
    agent_profile: str | None = None
    api_key_prefix: str | None = None
    default_space_id: str | None = None
    is_connected: bool | None = None
    focus_space_id: str | None = None
    metadata: dict[str, Any] | None = None
    last_seen_at: str | None = None
    created_at: str
    updated_at: str
```
16 fields. Matches § 5.1 exactly.

### Phase G — baseline pytest + pyright (reproduced for freeze)

```
$ .venv/bin/python -m pytest
124 tests collected
15 failed, 109 passed in 3.17s

$ .venv/bin/python -m pyright
12 errors, 0 warnings, 0 informations
```

## 17. Ship gates

- `.venv/bin/python -m pytest` → 117 collected, 0 failed, 117 passed.
- `.venv/bin/python -m pyright` → ≤ 12 errors, all in `mcp_adapter.py` + `test_launch.py` (no new errors in `tests/test_scaffold.py`, `tests/test_provision.py`, `tests/test_auth.py`, `tests/test_templates.py`).
- `git diff main -- src/` empty (no source changes).
- `git ls-files tests/test_example.py` empty (deleted).
- No respx mock stubs paths containing `/api/spaces/{...}/participants` remain in any test file.
- `/api/actors/me/agents` is the new endpoint stubbed in `_stub_backend` and in the inline stub block of `test_init_rotate_key_failure_does_not_persist`.

## 18. Security considerations

- **No auth boundary changes.** All mocked endpoints are authenticated behind `Depends(require_actor)` on the backend; the tests already emit a PAT-bearing `store_credential` fixture.
- **No user-input sanitization surfaces touched.** The `_actor_dict` helper embeds literal ASCII strings only; no template interpolation against user data.
- **No secrets in mocks.** `api_key_prefix="convo_ke"` and `api_key="convo_key_live_{role}"` are clearly test-only patterns (do not match the production key prefix scheme — production uses 8-char prefixes of live keys, which start with `convo_`). Consider `convo_key_live_*` fixture values flagged as test-mock tokens by any CI secret scanner; no change needed here.
- **Phantom endpoint finding (F2)** is a security-adjacent finding: `cmd_provision` silently fails in production. Users will not successfully provision agents via this path and may fall through to other flows. Not in scope this run; flag to Product.

## 19. Open questions

**None are blocking.** All design calls are resolved in-draft (D1/D2/D3).

F1, F2 are findings for Product's follow-up, not decisions blocking this run. Spec will raise them in the retro.

---

*Spec frozen @ `1546cf9`. Ready for Impl. Three-stage incremental plan (§ 13); every stage is independently testable; no folding.*
