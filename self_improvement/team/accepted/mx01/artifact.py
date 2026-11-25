# artifact.py
import hashlib
import re


def normalize(text: str) -> str:
    """Normalize text: lowercase, collapse whitespace runs to single space, strip."""
    if not text:
        return ""
    collapsed = re.sub(r"\s+", " ", text)
    return collapsed.strip().lower()


def sha256_hex_prefix(input_bytes: bytes, length: int) -> str:
    """Return first `length` hex characters of SHA256 hash."""
    return hashlib.sha256(input_bytes).hexdigest()[:length]


def item_id(kind: str, source: str, text: str) -> str:
    """
    Return SHA256 hex[:16] of kind + NUL + source + NUL + normalized text.
    
    Normalization: lowercase, collapse whitespace runs to single space, strip.
    Empty text is allowed (normalizes to empty string).
    """
    normalized = normalize(text)
    hash_input = kind + "\x00" + source + "\x00" + normalized
    return sha256_hex_prefix(hash_input.encode("utf-8"), 16)