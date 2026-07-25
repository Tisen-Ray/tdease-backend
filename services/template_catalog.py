"""Read-only workflow templates deployed by the server."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


def project_template(root: Path) -> dict[str, Any]:
    manifest_path, snakefile = root / "template.yaml", root / "Snakefile"
    if not manifest_path.is_file() or not snakefile.is_file():
        raise ValueError("template.yaml and Snakefile are required")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    template_id = manifest.get("id")
    if not isinstance(template_id, str) or not template_id:
        raise ValueError("template.yaml requires id")
    digest = hashlib.sha256()
    files = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(content)
        if relative == "Snakefile" or relative == "config.yaml" or relative.startswith("scripts/"):
            files[relative] = content.decode("utf-8")
    return {
        "id": template_id,
        "version": str(manifest.get("version", "1")),
        "name": str(manifest.get("name", template_id)),
        "description": str(manifest.get("description", "")),
        "nodes": manifest.get("nodes", []),
        "digest": digest.hexdigest(),
        "files": files,
        "readme": (root / "README.md").read_text(encoding="utf-8") if (root / "README.md").is_file() else "",
    }


def scan_templates(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not root.is_dir():
        return [], []
    templates, errors = [], []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        try:
            templates.append(project_template(directory))
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
            errors.append({"path": directory.name, "error": str(exc)})
    if len({item["id"] for item in templates}) != len(templates):
        errors.append({"path": root.as_posix(), "error": "duplicate template id"})
    return templates, errors
