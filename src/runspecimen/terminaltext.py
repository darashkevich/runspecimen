"""Refuse and escape terminal-control / invisible-format characters.

Contract validation refuses these characters in argv (and other
contract/workspace strings). Display code also escapes them so a value that
slipped past validation cannot rewrite a TTY (approve review, pretty output,
errors, status, verify). JSON default output does not use this helper.

This dual approach is intentional: refuse at parse time, escape on display.
"""

from __future__ import annotations

import unicodedata

# Bidi overrides and isolates that can reorder visible text.
_BIDI = frozenset(range(0x202A, 0x202F)) | frozenset(range(0x2066, 0x206A))

UNSAFE_DISPLAY_REFUSAL = (
    "must not contain terminal control or invisible format characters"
)


def is_unsafe_display_char(ch: str) -> bool:
    """True for C0/C1 controls, DEL, bidi overrides, and other format chars."""
    cp = ord(ch)
    if cp < 0x20 or (0x7F <= cp <= 0x9F):
        return True
    if cp in _BIDI:
        return True
    return unicodedata.category(ch) in {"Cc", "Cf", "Cs", "Co", "Zl", "Zp"}


def has_unsafe_display_chars(value: str) -> bool:
    return any(is_unsafe_display_char(ch) for ch in value)


def escape_for_terminal(value: str) -> str:
    """Make C0/C1/DEL/bidi/format characters visible (e.g. ``\\x1b``, ``\\u202e``).

    Argument boundaries stay with the caller (``shlex.join`` of already-escaped
    argv elements). ASCII graphic text is unchanged, so N10 and unknown-field
    refusals keep their exact bytes.
    """
    out: list[str] = []
    for ch in value:
        if not is_unsafe_display_char(ch):
            out.append(ch)
            continue
        cp = ord(ch)
        if cp <= 0xFF:
            out.append(f"\\x{cp:02x}")
        elif cp <= 0xFFFF:
            out.append(f"\\u{cp:04x}")
        else:
            out.append(f"\\U{cp:08x}")
    return "".join(out)
