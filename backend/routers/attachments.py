import os
import uuid
import aiofiles
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..schemas import AttachmentOut
from ..auth_utils import get_current_user, require_role

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))

# Entity types an attachment may be bound to. Restricting this also constrains
# the on-disk directory name, closing the path-traversal vector below.
ALLOWED_ENTITY_TYPES = {"test", "step", "run_case"}

# Extension allow-list (SECURITY M-2). Test-evidence formats only: images,
# video, documents, logs/reports, archives. Extends via env, e.g.
# UPLOAD_EXTRA_EXTENSIONS=".psd,.sketch". Notably absent: .html/.svg (render
# as markup → stored XSS), executables, scripts.
ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".mp4", ".webm", ".mov",
    ".pdf", ".txt", ".log", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".har", ".zip", ".gz", ".xlsx", ".docx",
}
ALLOWED_EXTENSIONS |= {
    e.strip().lower()
    for e in os.getenv("UPLOAD_EXTRA_EXTENSIONS", "").split(",")
    if e.strip().startswith(".")
}

# The filename extension and declared media type must agree. This is not used
# to render content inline (downloads are always attachments + nosniff), but it
# prevents obviously disguised executable/active content from entering the
# evidence store. Custom extensions require an explicit custom MIME allow-list.
_MIME_BY_EXTENSION = {
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"},
    ".gif": {"image/gif"}, ".webp": {"image/webp"},
    ".bmp": {"image/bmp", "image/x-ms-bmp"},
    ".mp4": {"video/mp4"}, ".webm": {"video/webm"},
    ".mov": {"video/quicktime"},
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"}, ".log": {"text/plain"},
    ".md": {"text/plain", "text/markdown"},
    ".csv": {"text/csv", "application/csv"},
    ".json": {"application/json", "text/json"},
    ".xml": {"application/xml", "text/xml"},
    ".yaml": {"application/yaml", "application/x-yaml", "text/yaml", "text/x-yaml"},
    ".yml": {"application/yaml", "application/x-yaml", "text/yaml", "text/x-yaml"},
    ".har": {"application/json"},
    ".zip": {"application/zip", "application/x-zip-compressed"},
    ".gz": {"application/gzip", "application/x-gzip"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
}
_EXTRA_MIME_TYPES = {
    value.strip().lower()
    for value in os.getenv("UPLOAD_EXTRA_MIME_TYPES", "").split(",")
    if value.strip()
}

# Types a browser will render inline with active content — never echo these
# back as their claimed MIME type on download.
_NEVER_INLINE_MIME = {"text/html", "application/xhtml+xml", "image/svg+xml"}

router = APIRouter(tags=["attachments"])

WRITE_ROLES = require_role("admin", "manager", "tester")


def _safe_component(value: str) -> str:
    """Reject any value that could escape UPLOAD_DIR when used as a path part."""
    value = (value or "").strip()
    if not value or "/" in value or "\\" in value or value in (".", "..") or "\x00" in value:
        raise HTTPException(status_code=422, detail="Invalid path component")
    return value


def _attachment_path(storage_path: str) -> str:
    """Resolve a stored relative path without ever escaping the upload root."""
    upload_root = os.path.realpath(UPLOAD_DIR)
    abs_path = os.path.realpath(os.path.join(upload_root, storage_path or ""))
    try:
        inside = os.path.commonpath([upload_root, abs_path]) == upload_root
    except ValueError:
        inside = False
    if not inside:
        raise HTTPException(status_code=404, detail="File not found on disk")
    return abs_path


@router.get("/attachments", response_model=List[AttachmentOut])
def list_attachments(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Attachment)
        .filter(
            models.Attachment.entity_type == entity_type,
            models.Attachment.entity_id == entity_id,
        )
        .all()
    )


@router.post("/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    entity_type: str = Form(...),
    entity_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = WRITE_ROLES,
):
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="Invalid entity_type")
    # entity_id and the stored filename must not be able to walk out of UPLOAD_DIR.
    safe_entity_id = _safe_component(str(entity_id))

    ext = os.path.splitext(os.path.basename(file.filename or ""))[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"File type '{ext or '(none)'}' not allowed. Allowed: "
                   + ", ".join(sorted(ALLOWED_EXTENSIONS)),
        )
    declared_mime = (file.content_type or "").split(";", 1)[0].strip().lower()
    allowed_mimes = _MIME_BY_EXTENSION.get(ext, _EXTRA_MIME_TYPES)
    if not declared_mime or declared_mime not in allowed_mimes:
        raise HTTPException(
            status_code=422,
            detail=f"MIME type '{declared_mime or '(none)'}' is not allowed for {ext}",
        )

    content = await file.read()  # read stream ONCE
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_UPLOAD_MB}MB limit",
        )

    # Store relative path — safe for Docker and moves. The on-disk name is a
    # random UUID plus only the client filename's *basename*, so a filename like
    # "../../etc/passwd" can't traverse; the original name is kept in the DB.
    rel_dir = os.path.join(entity_type, safe_entity_id)
    abs_dir = os.path.join(UPLOAD_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    client_basename = os.path.basename(file.filename or "")
    safe_filename = f"{uuid.uuid4().hex}_{client_basename}"
    rel_path = os.path.join(rel_dir, safe_filename)
    abs_path = os.path.join(UPLOAD_DIR, rel_path)

    # Defense in depth: refuse if the resolved path escapes UPLOAD_DIR.
    upload_root = os.path.realpath(UPLOAD_DIR)
    if os.path.commonpath([upload_root, os.path.realpath(abs_path)]) != upload_root:
        raise HTTPException(status_code=422, detail="Invalid attachment path")

    async with aiofiles.open(abs_path, "wb") as f:
        await f.write(content)

    att = models.Attachment(
        entity_type=entity_type,
        entity_id=str(entity_id),
        filename=file.filename,
        mime_type=declared_mime,
        storage_path=rel_path,
        uploaded_by=current_user.id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


@router.get("/attachments/{att_id}")
def download_attachment(att_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    att = db.query(models.Attachment).filter(models.Attachment.id == att_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    abs_path = _attachment_path(att.storage_path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    # filename= makes FileResponse emit Content-Disposition: attachment.
    # Client-declared MIME is untrusted: renderable-markup types are forced to
    # octet-stream so a spoofed content_type can't turn a download into a page.
    mime = att.mime_type or "application/octet-stream"
    if mime.split(";")[0].strip().lower() in _NEVER_INLINE_MIME:
        mime = "application/octet-stream"
    return FileResponse(
        path=abs_path,
        filename=att.filename,
        media_type=mime,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/attachments/{att_id}", status_code=204)
def delete_attachment(att_id: int, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    att = db.query(models.Attachment).filter(models.Attachment.id == att_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    abs_path = _attachment_path(att.storage_path)
    if os.path.exists(abs_path):
        os.remove(abs_path)
    db.delete(att)
    db.commit()
