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
for scientific computation (Rust `tdease-ms` CLI + Agent Skills) but **does not
contain** scientific algorithms itself — those live in the capability toolkit.

## Quick start

```bash
git clone https://github.com/Tisen-Ray/tdease-backend.git
cd tdease-backend
uv sync

# Run the dev server
uv run uvicorn app.main:app --reload --port 8000
```

Requires Python ≥3.11, <3.15. Uses [uv](https://docs.astral.sh/uv/) for
dependency management (`uv.lock` is the lockfile).

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
