# tdease-backend

TDEase Python backend — a FastAPI server providing Snakemake execution,
Run lifecycle management, file storage, and authentication for the TDEase
mass-spectrometry analysis platform. It is one component of
[TDEaseNexus](https://github.com/Tisen-Ray/TDEaseNexus), the desktop
application this backend serves.

## What this is

| Module | Responsibility |
|--------|---------------|
| `app/` | FastAPI application: HTTP API surface, server entrypoint, database models |
| `src/` | Execution runtime: Snakemake engine, storage layer, workspace containment, backend settings |
| `cli.py` | Public command-line entrypoint (`serve`, `worker` subcommands) |

The backend consumes [tdease-ai-capability](https://github.com/Tisen-Ray/tdease-ai-capability)
for scientific computation (Rust `tdeasenexus-toolbox` CLI + Agent Skills) but **does not
contain** scientific algorithms itself — those live in the capability toolkit.

```
Desktop (Electron)
  └── starts / connects to this Backend
        └── calls tdease-ai-capability (Rust CLI + skills) for computation
```

The backend can run standalone (server mode) without the Electron desktop
client. It serves the same HTTP API in both Desktop and Server deployments.

Run lifecycle: the API accepts Run submissions and persists them; a supervised
worker process (`tdease-backend worker`) claims queued Runs and drives the
Snakemake engine. The worker is a stateless poller — claims are reconciled from
the Journal on startup, so restarting it is safe. Under `serve`, the CLI keeps
one worker alive and fails loudly (shutting the API down) after three crashes
inside a minute, so a stuck Run never looks "ready but idle".

## Quick start

```bash
git clone https://github.com/Tisen-Ray/tdease-backend.git
cd tdease-backend
uv sync

# Run the complete service (API + Worker)
uv run tdease-backend serve --config ./backend.json
```

Requires Python ≥3.11, <3.15. Uses [uv](https://docs.astral.sh/uv/) for
dependency management (`uv.lock` is the lockfile).

```bash
uv run pytest    # test suite (28 tests at time of writing)
```

## Authentication

Two modes, set via `auth.mode` in `backend.json`:

- `local` — tokenless, **loopback binds only**. `cli.py` fails closed on
  startup if `auth.mode=local` is paired with a non-loopback `server.host`;
  bearer auth is required to leave localhost.
- `bearer` — token authentication, required for any non-loopback deployment.

Runtime data is external to this repository. The service owns its data layout and may
consume the Scientific System only through public commands or protocols; it never imports
Desktop implementation paths.

The node catalog belongs to Backend data. If Backend `dataRoot` is
`<TDEaseNexus-Data>/backend`, packages live at
`<TDEaseNexus-Data>/backend/nodes/`. Desktop/System remains a separate root at
`<TDEaseNexus-Data>/system/`. The catalog root is derived from `dataRoot` and a
path outside it is rejected at startup. Production does not use
environment-variable path discovery.

Minimal `backend.json`:

```json
{
  "schemaVersion": 1,
  "environment": "development",
  "deploymentMode": "local",
  "dataRoot": "./data",
  "server": { "host": "127.0.0.1", "port": 0 },
  "auth": { "mode": "local" },
  "logging": { "level": "INFO" },
  "resources": {}
}
```

Production reads no `TDEASE_*` variables. Development/test overrides are accepted only
when `--allow-env-overrides` is explicitly supplied.

## Dependencies

See `pyproject.toml` (package `tdease-backend` v0.2.0). Key groups:
- **Web**: FastAPI, Uvicorn, Pydantic
- **Workflow**: Snakemake 9.x, pinned to 9.23.1 (+ interface plugins)
- **Data**: pandas, polars, numpy, scipy, pyteomics, massql

## License

GPL-3.0-or-later (see `LICENSE`; also declared in `pyproject.toml`).
