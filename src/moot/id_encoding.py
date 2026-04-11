"""Crockford Base32 ID encoding for typed entity IDs.

Convo uses random BIGINT primary keys internally, encoded as prefixed
Crockford Base32 strings in external representations (APIs, logs, URLs).

    usr_7zy2kf9x   →  type prefix + Crockford Base32 of the BIGINT
    agt_3nm8qw4r

Encoding rules: if it leaves Python or PostgreSQL, encode it.
"""

from __future__ import annotations

import secrets

# Crockford Base32 alphabet (lowercase, excludes I L O U)
CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"

# Reverse lookup for decoding
_DECODE_MAP: dict[str, int] = {c: i for i, c in enumerate(CROCKFORD)}

# Known entity prefixes
PREFIXES = frozenset({
    "usr", "agt", "mem", "ten", "spc", "evt", "inv",
    "dec", "qst", "thr", "sum", "lnk", "tmr", "arc",
})


def generate_id() -> int:
    """Generate a random positive BIGINT (63 bits → positive i64)."""
    return secrets.randbits(63)


def encode_id(value: int, prefix: str) -> str:
    """Encode a BIGINT as a prefixed Crockford Base32 string.

    >>> encode_id(83419274652, "usr")
    'usr_2dp2t7cw'
    """
    if value < 0:
        raise ValueError(f"ID must be non-negative, got {value}")
    if prefix not in PREFIXES:
        raise ValueError(f"Unknown prefix '{prefix}', expected one of {sorted(PREFIXES)}")
    if value == 0:
        return f"{prefix}_0"
    chars: list[str] = []
    v = value
    while v > 0:
        chars.append(CROCKFORD[v & 0x1F])
        v >>= 5
    return f"{prefix}_{''.join(reversed(chars))}"


def decode_id(encoded: str, expected_prefix: str) -> int:
    """Decode a prefixed Crockford Base32 string to a BIGINT.

    >>> decode_id("usr_2dp2t7cw", "usr")
    83419274652
    """
    if expected_prefix not in PREFIXES:
        raise ValueError(
            f"Unknown prefix '{expected_prefix}', expected one of {sorted(PREFIXES)}"
        )
    prefix, sep, b32 = encoded.partition("_")
    if not sep:
        raise ValueError(f"Invalid encoded ID (missing '_' separator): {encoded!r}")
    if prefix != expected_prefix:
        raise ValueError(f"Expected prefix '{expected_prefix}', got '{prefix}'")
    if not b32:
        raise ValueError(f"Invalid encoded ID (empty value): {encoded!r}")
    value = 0
    for c in b32:
        cl = c.lower()
        if cl not in _DECODE_MAP:
            raise ValueError(f"Invalid Crockford Base32 character: {c!r}")
        value = (value << 5) | _DECODE_MAP[cl]
    return value
