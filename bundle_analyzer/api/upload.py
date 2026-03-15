"""Streaming file upload handler for large support bundles.

Handles bundles up to 500MB+ by streaming chunks to disk
rather than buffering the entire file in memory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile
from loguru import logger

# 64KB chunk size for streaming writes
_CHUNK_SIZE = 64 * 1024
_DEFAULT_MAX_UPLOAD_MB = 1024
_ALLOWED_SUFFIXES = (".tar.gz", ".tgz", ".tar")

# Default upload directory (created lazily)
_UPLOAD_DIR: Path | None = None


def _get_upload_dir() -> Path:
    """Return (and lazily create) the upload directory.

    Returns:
        Path to the persistent upload directory.
    """
    global _UPLOAD_DIR
    if _UPLOAD_DIR is None:
        _UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="bundle_uploads_"))
        logger.info("Upload directory: {}", _UPLOAD_DIR)
    return _UPLOAD_DIR


async def save_upload(upload: UploadFile) -> Path:
    """Stream an uploaded file to disk without buffering in memory.

    Args:
        upload: The FastAPI UploadFile from the request.

    Returns:
        Path to the saved file on disk.

    Raises:
        IOError: If writing fails.
    """
    upload_dir = _get_upload_dir()
    filename = upload.filename or "bundle.tar.gz"
    max_upload_mb = int(os.environ.get("MAX_UPLOAD_MB", _DEFAULT_MAX_UPLOAD_MB))
    max_bytes = max_upload_mb * 1024 * 1024

    if not filename.endswith(_ALLOWED_SUFFIXES):
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. Expected one of: "
                + ", ".join(_ALLOWED_SUFFIXES)
            ),
        )

    # Sanitise filename -- strip directory components
    safe_name = Path(filename).name
    dest = upload_dir / safe_name

    # Avoid collisions by appending a suffix
    counter = 0
    stem = dest.stem
    suffix = dest.suffix
    while dest.exists():
        counter += 1
        dest = upload_dir / f"{stem}_{counter}{suffix}"

    bytes_written = 0
    try:
        with open(dest, "wb") as f:
            while True:
                chunk = await upload.read(_CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds MAX_UPLOAD_MB={max_upload_mb}",
                    )
    except OSError as exc:
        logger.error("Failed to save upload to {}: {}", dest, exc)
        # Clean up partial file
        if dest.exists():
            dest.unlink()
        raise

    logger.info(
        "Saved upload {} ({:.1f} MB) to {}",
        safe_name,
        bytes_written / (1024 * 1024),
        dest,
    )
    return dest
