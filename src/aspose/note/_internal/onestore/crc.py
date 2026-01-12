from __future__ import annotations

import binascii


def crc32_rfc3309(data: bytes) -> int:
    """CRC32 per RFC3309-style parameters used by .one in MS-ONESTORE.

    Practically, this matches the common IEEE reflected CRC-32 implementation.
    In Python, `binascii.crc32()` already produces the expected values.
    """
    return binascii.crc32(data) & 0xFFFFFFFF


def mso_crc32_compute(data: bytes) -> int:
    """MS-OSHARED MsoCrc32Compute (used by .onetoc2).

    Not implemented yet (will be needed once .onetoc2 parsing is added).
    """
    raise NotImplementedError("MsoCrc32Compute is not implemented yet")
