import re
from pathlib import Path
from typing import Tuple
from backend.config import settings

# Magic byte signatures
MAGIC_BYTES = {
    b"%PDF": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}

def sanitize_filename(filename: str) -> str:
    """Removes path separators and non-standard characters from filename."""
    base_name = Path(filename).name
    # Keep only alphanumeric, hyphens, underscores, dots
    cleaned = re.sub(r"[^\w\s\.-]", "", base_name).strip()
    return cleaned or "unnamed_document"

def get_file_extension(filename: str) -> str:
    """Returns normalized lowercase extension with dot."""
    ext = Path(filename).suffix.lower()
    return ext

def validate_file_extension(filename: str) -> bool:
    ext = get_file_extension(filename)
    return ext in settings.allowed_extensions_list

def validate_magic_bytes(header: bytes) -> Tuple[bool, str]:
    """Validates the file signature (magic bytes) against known document types."""
    if header.startswith(b"%PDF"):
        return True, "application/pdf"
    if header.startswith(b"\xff\xd8\xff"):
        return True, "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return True, "image/png"
    return False, "application/octet-stream"

def is_valid_file_size(size_bytes: int) -> bool:
    return 0 < size_bytes <= settings.max_file_size_bytes
