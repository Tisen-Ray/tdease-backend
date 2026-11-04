<p align="center">
  <img src="https://raw.githubusercontent.com/Tisen-Ray/TDEaseNexus/main/assets/logo.png" width="96" alt="TDEaseNexus logo">
</p>

# tdease-backend

Python/FastAPI execution service behind
[TDEaseNexus](https://github.com/Tisen-Ray/TDEaseNexus): Run lifecycle, Snakemake
pipeline execution, storage, and server policy. Scientific computation lives in
[tdease-ai-capability](https://github.com/Tisen-Ray/tdease-ai-capability); this
service never implements algorithms itself.

It runs standalone — the desktop client is just one consumer of the same HTTP API,
so server deployments work without Electron.

## Run

```bash
git clone https://github.com/Tisen-Ray/tdease-backend.git
cd tdease-backend
uv sync
uv run tdease-backend serve --config ./backend.json
```

Requires Python ≥3.11, <3.15. `serve` starts the HTTP API plus one supervised worker
and shuts down loudly if that worker crashes three times within a minute.
`tdease-backend worker` runs a bare worker against the same database; it is safe to
restart because queued claims are reconciled from the Journal on startup.

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

`auth.mode`: `local` is tokenless and loopback-only — startup fails closed if
paired with a non-loopback `server.host`; `bearer` is required for any non-loopback
deployment. Runtime data lives outside this repository: the node catalog sits in
`<dataRoot>/backend/nodes/`, and a catalog path outside `dataRoot` is rejected at
startup.

## Layout

| Path | Responsibility |
|------|----------------|
| `app/` | HTTP API surface, server entrypoint, database models |
| `src/` | Snakemake engine, storage, workspace containment, backend settings |
| `cli.py` | `serve` / `worker` command-line entrypoints |

```bash
uv run pytest
```

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
