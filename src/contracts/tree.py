"""
Tree Manifest — the lossless path-tree truth.

Blobs are content-addressed bytes; a Tree manifest is the path→blob mapping.
A tree cannot be reconstructed from a bare blob store: file names, directory
structure, and permissions live in the tree.

Analogy: Git tree objects. Blob = file content, Tree = file name + mode.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _validate_path_no_traversal(v: str) -> str:
    """Reject path traversal patterns."""
    if v.startswith("/") or v.startswith("\\"):
        raise ValueError(f"Absolute paths are not allowed: {v}")
    if v.startswith("../") or v.startswith("..\\") or v == "..":
        raise ValueError(f"Path traversal is not allowed: {v}")
    if "/../" in v or "\\..\\" in v:
        raise ValueError(f"Path traversal is not allowed: {v}")
    return v


class TreeEntry(BaseModel):
    """
    One entry in a Tree — a file or symbolic link.

    Directories are not represented by entries; directory structure is implied
    by the / separators in path.
    """

    path: str = Field(
        description="Path relative to the workspace root, using / separators.",
        min_length=1,
        max_length=4096,
    )
    _validate_path = field_validator("path")(_validate_path_no_traversal)
    blob_hash: str = Field(
        description="sha256 hex digest (64 hex chars)",
        pattern=r"^[a-f0-9]{64}$",
    )
    size: int = Field(description="File size in bytes", ge=0)
    mode: Literal["file", "symlink"] = Field(
        default="file",
        description="Entry type",
    )
    executable: bool = Field(default=False, description="Executable bit")


class TreeManifest(BaseModel):
    """
    Immutable tree manifest.

    Storage: data-root/store/<tree_hash>  (content-addressed)
    Reference: Run commit → tree_hash (locks the workspace state at submission time)
    """

    tree_hash: str = Field(
        default="",
        description="sha256(sorted(json(entries))), populated by freeze()",
    )
    workspace_id: str = Field(description="Owning workspace")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    entries: list[TreeEntry] = Field(
        description="Sorted entry list",
    )
    parent_tree_hash: Optional[str] = Field(
        default=None,
        description="Previous tree hash, forming a chained history",
    )

    def freeze(self) -> str:
        """
        Compute and freeze the tree hash.

        hash = sha256(canonical JSON of entries).
        Canonicalization: sort by path, serialize each entry as compact JSON
        {path,blob_hash,size,mode,executable}.
        """
        import hashlib
        import json

        sorted_entries = sorted(self.entries, key=lambda e: e.path)
        canonical: list[dict] = [
            {
                "p": e.path,
                "h": e.blob_hash,
                "s": e.size,
                "m": e.mode,
                "x": e.executable,
            }
            for e in sorted_entries
        ]
        serialized = json.dumps(canonical, separators=(",", ":"), sort_keys=True)
        self.tree_hash = hashlib.sha256(serialized.encode()).hexdigest()
        return self.tree_hash


class TreeDiff(BaseModel):
    """
    Difference between two trees — the data model for the frontend diff view.
    Not computed by the backend; the frontend/CLI generates it by comparing two
    tree manifests.
    """

    added: list[TreeEntry] = Field(default_factory=list)
    removed: list[TreeEntry] = Field(default_factory=list)
    modified: list[TreeEntry] = Field(default_factory=list)
    unchanged: int = Field(default=0)
