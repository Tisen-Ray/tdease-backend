"""Content-addressed upload handshake used by CLI/Desktop clients."""
from __future__ import annotations

import re

from fastapi import APIRouter, Body, File, HTTPException, UploadFile

from src.contracts import TreeEntry
from src.execution_runtime.storage import get_storage

router = APIRouter(prefix="/api/v2/uploads", tags=["uploads"])
_DIGEST = re.compile(r"^[a-f0-9]{64}$")


@router.post("/manifest")
async def negotiate_manifest(entries: list[TreeEntry] = Body(..., embed=True)):
    storage = get_storage()
    missing = sorted({entry.blob_hash for entry in entries if not storage.blob_exists(entry.blob_hash)})
    return {"missing": missing, "accepted": len(entries)}


@router.put("/{digest}")
async def upload_blob(digest: str, file: UploadFile = File(...)):
    if not _DIGEST.fullmatch(digest):
        raise HTTPException(status_code=400, detail="invalid sha256 digest")
    try:
        stored, size = get_storage().blob_put_stream(file.file, digest)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()
    return {"sha256": stored, "size": size}
