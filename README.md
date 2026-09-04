# tdease-backend

TDEase Python backend — a FastAPI server providing Snakemake execution,
Run lifecycle management, file storage, and authentication for the TDEase
mass-spectrometry analysis platform.

## What this is

| Module | Responsibility |
|--------|---------------|
| `app/` | FastAPI application: HTTP API surface, server entrypoint, database models |
| `src/` | Execution runtime: Snakemake engine, storage layer, workspace containment, backend settings |

The backend consumes [tdease-ai-capability](https://github.com/Tisen-Ray/tdease-ai-capability)
for scientific computation (Rust `tdnexus-toolbox` CLI + Agent Skills) but **does not
contain** scientific algorithms itself — those live in the capability toolkit.

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

Runtime data is external to this repository. The service owns its data layout and may
consume the Scientific System only through public commands or protocols; it never imports
Desktop implementation paths.

The node catalog lives at `<dataRoot>/nodes/` — one deployment root, no separate
wiring to forget. The optional JSON `nodeRoot` field is for deployments that keep
read-only assets away from the data root (the packaged desktop pins it to its
resources tree); production does not use environment-variable path discovery.

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

## Architecture

```
Desktop (Electron)
  └── starts / connects to this Backend
        └── calls tdease-ai-capability (Rust CLI + skills) for computation
```

The backend can run standalone (server mode) without the Electron desktop
client. It serves the same HTTP API in both Desktop and Server deployments.

## Dependencies

See `pyproject.toml`. Key groups:
- **Web**: FastAPI, Uvicorn, Pydantic
- **Workflow**: Snakemake 9.x (+ interface plugins)
- **Data**: pandas, polars, numpy, scipy, pyteomics, massql
