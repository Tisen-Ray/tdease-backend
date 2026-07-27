"""
Tree Manifest — 不可丢失的路径树真相。

Blob 是内容寻址的字节，Tree manifest 是 path→blob 的映射。
不能从裸 blob store 反推 tree：文件名、目录结构、权限都在 tree 里。

类比：Git tree objects。Blob = 文件内容，Tree = 文件名+模式。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _validate_path_no_traversal(v: str) -> str:
    """拒绝路径穿越模式。"""
    if v.startswith("/") or v.startswith("\\"):
        raise ValueError(f"绝对路径不允许: {v}")
    if v.startswith("../") or v.startswith("..\\") or v == "..":
        raise ValueError(f"路径穿越不允许: {v}")
    if "/../" in v or "\\..\\" in v:
        raise ValueError(f"路径穿越不允许: {v}")
    return v


class TreeEntry(BaseModel):
    """
    Tree 中的一个条目 — 文件或符号链接。

    目录不由条目表示；目录结构由 path 的 / 分隔隐式表达。
    """

    path: str = Field(
        description="相对于 workspace root 的路径，使用 / 分隔符。",
        min_length=1,
        max_length=4096,
    )
    _validate_path = field_validator("path")(_validate_path_no_traversal)
    blob_hash: str = Field(
        description="sha256 hex digest (64 hex chars)",
        pattern=r"^[a-f0-9]{64}$",
    )
    size: int = Field(description="文件大小（字节）", ge=0)
    mode: Literal["file", "symlink"] = Field(
        default="file",
        description="条目类型",
    )
    executable: bool = Field(default=False, description="可执行位")


class TreeManifest(BaseModel):
    """
    不可变 tree manifest。

    存储位置: data-root/store/<tree_hash>  (内容寻址)
    引用关系: Run commit → tree_hash（锁定 workspace 在提交时刻的状态）
    """

    tree_hash: str = Field(
        default="",
        description="sha256(sorted(json(entries)))，填充于 freeze()",
    )
    workspace_id: str = Field(description="所属 workspace")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    entries: list[TreeEntry] = Field(
        description="排序后的条目列表",
    )
    parent_tree_hash: Optional[str] = Field(
        default=None,
        description="上一版 tree hash，形成链式历史",
    )

    def freeze(self) -> str:
        """
        计算 tree hash 并固化。

        hash = sha256(entries 的规范化 JSON)。
        规范化规则：按 path 排序，每个 entry 序列化为
        {path,blob_hash,size,mode,executable} 的紧凑 JSON。
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
    两个 tree 之间的差异 — 前端 diff 视图的数据模型。
    不由后端计算；前端/CLI 比对两个 tree manifest 后生成。
    """

    added: list[TreeEntry] = Field(default_factory=list)
    removed: list[TreeEntry] = Field(default_factory=list)
    modified: list[TreeEntry] = Field(default_factory=list)
    unchanged: int = Field(default=0)
