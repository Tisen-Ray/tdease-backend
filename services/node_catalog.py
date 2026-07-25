"""Single read-only catalog for executable node packages deployed by the server."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml


def package_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def project_package(package_dir: Path) -> dict[str, Any]:
    manifest_path = package_dir / "package.yaml"
    if not manifest_path.is_file():
        raise ValueError("package.yaml is required")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    node_id, version = manifest.get("id"), manifest.get("version")
    if not isinstance(node_id, str) or not node_id or not isinstance(version, (str, int, float)):
        raise ValueError("package.yaml requires id and version")
    rules = manifest.get("rules", [])
    return {
        "id": node_id,
        "version": str(version),
        "digest": package_digest(package_dir),
        "platforms": manifest.get("platforms", []),
        "description": manifest.get("description", ""),
        "inputs": manifest.get("inputs", []),
        "outputs": manifest.get("outputs", []),
        "rules": rules if isinstance(rules, list) else [],
        "entrypoints": manifest.get("entrypoints", {}),
        "rules_text": (package_dir / "rules.smk").read_text(encoding="utf-8") if (package_dir / "rules.smk").is_file() else "",
        "readme": (package_dir / "README.md").read_text(encoding="utf-8") if (package_dir / "README.md").is_file() else "",
        "package_dir": package_dir,
    }


def scan_nodes(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not root.is_dir():
        return [], []
    nodes, errors = [], []
    for package_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        try:
            nodes.append(project_package(package_dir))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append({"path": package_dir.name, "error": str(exc)})
    if len({node["id"] for node in nodes}) != len(nodes):
        errors.append({"path": root.as_posix(), "error": "duplicate node id"})
    return nodes, errors


def platform_id() -> str:
    os_name = "win" if sys.platform == "win32" else "linux" if sys.platform.startswith("linux") else "macos"
    return f"{os_name}-x64"


def resolve_bindings(root: Path, bindings: list[Any]) -> list[tuple[Any, dict[str, Any]]]:
    nodes, errors = scan_nodes(root)
    if errors:
        raise ValueError(f"invalid node catalog: {errors}")
    by_id = {node["id"]: node for node in nodes}
    resolved = []
    for binding in bindings:
        node = by_id.get(binding.id)
        if not node:
            raise ValueError(f"node not found: {binding.id}")
        if node["version"] != binding.version or node["digest"] != binding.digest:
            raise ValueError(f"node identity changed: {binding.id}")
        if node["platforms"] and platform_id() not in node["platforms"]:
            raise ValueError(f"node does not support {platform_id()}: {binding.id}")
        unknown = sorted(set(binding.rules) - set(node["rules"]))
        if unknown:
            raise ValueError(f"unknown node rules for {binding.id}: {unknown}")
        resolved.append((binding, node))
    return resolved


def materialize_bindings(target_root: Path, resolved: list[tuple[Any, dict[str, Any]]], atomic_write) -> None:
    for binding, node in resolved:
        atomic_write(target_root / "nodes" / binding.id / "rules.smk", node["rules_text"])
