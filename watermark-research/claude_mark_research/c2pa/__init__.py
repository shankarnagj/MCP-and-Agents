"""C2PA Content Credentials inspection (read-only).

C2PA is file-level cryptographic provenance metadata. It is entirely separate
from Claude's statistical *text* watermark and is never treated as such.
This package only reads and reports; it never creates, modifies, strips or
forges manifests or signatures.
"""

from .report import C2PA_ABSENT, C2PA_INVALID, C2PA_PRESENT, C2PA_UNVERIFIABLE, inspect_file

__all__ = ["inspect_file", "C2PA_PRESENT", "C2PA_ABSENT", "C2PA_INVALID", "C2PA_UNVERIFIABLE"]
