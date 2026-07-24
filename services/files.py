"""
File service — 路径守卫 + SHA-256 校验 + presigned URL 发放。

规则：
- 绝对路径拒止、../ 穿越拒止
- blob 写入前校验 digest
- 本地直接文件系统；远端 presigned URL
- 传输机制托管给 S3/MinIO，我们只生成 URL
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional

from src.contracts import (
    digest_mismatch,
    path_traversal,
    quota_exceeded,
)


# --- 路径守卫 ---

FORBIDDEN_PREFIXES = ("/", "\\")
FORBIDDEN_SEGMENTS = ("..",)
MAX_PATH_LENGTH = 4096


def guard_path(relative_path: str) -> str:
    """
    校验并规范化相对路径。违反 → AppError。

    规则：
    - 不能是绝对路径
    - 不能包含 .. 段
    - 长度 ≤ 4096
    - 统一使用 / 分隔符
    """
    # 绝对路径检查
    for prefix in FORBIDDEN_PREFIXES:
        if relative_path.startswith(prefix):
            raise path_traversal(relative_path)

    # 穿越检查
    segments = relative_path.replace("\\", "/").split("/")
    for seg in segments:
        if seg in FORBIDDEN_SEGMENTS:
            raise path_traversal(relative_path)

    # 长度检查
    if len(relative_path) > MAX_PATH_LENGTH:
        raise path_traversal(relative_path)

    # 规范化：统一为 /
    return relative_path.replace("\\", "/")


def guard_paths(paths: list[str]) -> list[str]:
    """批量校验，任一失败即抛异常。"""
    return [guard_path(p) for p in paths]


# --- Hash 工具 ---

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """计算文件 SHA-256（分块读取，大文件友好）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_digest(path: Path, expected_sha256: str) -> None:
    """文件 digest 不一致 → AppError。"""
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise digest_mismatch(str(path), expected_sha256, actual)


# --- Blob store（本地文件系统）---

def data_root() -> Path:
    return Path(os.environ.get("TDEASE_DATA_ROOT", "server-data"))


def blob_path(hash_hex: str) -> Path:
    """
    blob 存储路径: store/<prefix>/<hash>
    两层前缀减少单目录文件数。
    """
    return data_root() / "store" / hash_hex[:2] / hash_hex


def blob_put(data: bytes, expected_hash: str) -> str:
    """
    写入 blob。返回 hex hash。

    如果 blob 已存在 → 秒传（校验 hash）。
    如果 hash 不匹配 → AppError。
    """
    actual = sha256_hex(data)
    if actual != expected_hash:
        raise digest_mismatch("(blob)", expected_hash, actual)

    path = blob_path(actual)
    if path.exists():
        # 已存在：校验已有文件
        if sha256_file(path) != actual:
            # 磁盘损坏，覆盖
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return actual

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return actual


def blob_put_file(source: Path, expected_hash: str) -> str:
    """
    从本地文件写入 blob。校验 hash 后原子移动或引用。
    """
    actual = sha256_file(source)
    if actual != expected_hash:
        raise digest_mismatch(str(source), expected_hash, actual)

    dest = blob_path(actual)
    if dest.exists():
        return actual

    dest.parent.mkdir(parents=True, exist_ok=True)
    # 同文件系统内硬链接（节省空间）；不行则复制
    try:
        os.link(source, dest)
    except OSError:
        import shutil
        shutil.copy2(source, dest)
    return actual


def blob_exists(hash_hex: str) -> bool:
    return blob_path(hash_hex).exists()


def blob_read(hash_hex: str) -> bytes:
    path = blob_path(hash_hex)
    if not path.exists():
        from src.contracts import blob_not_found
        raise blob_not_found(hash_hex)
    return path.read_bytes()


# --- Presigned URL（MinIO/S3 托管传输）---

def presigned_put_url(
    blob_hash: str,
    content_type: str = "application/octet-stream",
    expires_seconds: int = 3600,
) -> str:
    """
    生成 presigned PUT URL — 客户端直传到 S3/MinIO。

    Desktop 模式 (TDEASE_STORAGE=local)：返回 null，客户端直接写本地。
    Cloud 模式 (TDEASE_STORAGE=s3)：通过 MinIO SDK 生成 presigned URL。
    """
    storage = os.environ.get("TDEASE_STORAGE", "local")
    if storage == "local":
        return ""  # 本地模式不需要 presigned URL

    # Cloud 模式：MinIO SDK
    try:
        from minio import Minio
        from minio.commonconfig import CopySource
    except ImportError:
        raise RuntimeError("MinIO SDK not installed. Run: pip install minio")

    endpoint = os.environ.get("TDEASE_S3_ENDPOINT", "localhost:9000")
    access_key = os.environ.get("TDEASE_S3_ACCESS_KEY", "")
    secret_key = os.environ.get("TDEASE_S3_SECRET_KEY", "")
    bucket = os.environ.get("TDEASE_S3_BUCKET", "tdease-store")
    secure = os.environ.get("TDEASE_S3_SECURE", "0") == "1"

    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    # 确保 bucket 存在
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    object_name = f"store/{blob_hash[:2]}/{blob_hash}"

    return client.presigned_put_object(
        bucket_name=bucket,
        object_name=object_name,
        expires=expires_seconds,
    )


def presigned_get_url(
    blob_hash: str,
    expires_seconds: int = 3600,
) -> str:
    """生成 presigned GET URL — 客户端从 S3/MinIO 下载。"""
    storage = os.environ.get("TDEASE_STORAGE", "local")
    if storage == "local":
        return f"file://{blob_path(blob_hash)}"

    from minio import Minio

    endpoint = os.environ.get("TDEASE_S3_ENDPOINT", "localhost:9000")
    access_key = os.environ.get("TDEASE_S3_ACCESS_KEY", "")
    secret_key = os.environ.get("TDEASE_S3_SECRET_KEY", "")
    bucket = os.environ.get("TDEASE_S3_BUCKET", "tdease-store")
    secure = os.environ.get("TDEASE_S3_SECURE", "0") == "1"

    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    object_name = f"store/{blob_hash[:2]}/{blob_hash}"

    return client.presigned_get_object(
        bucket_name=bucket,
        object_name=object_name,
        expires=expires_seconds,
    )
