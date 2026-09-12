"""Language-neutral artifact chunks, carried in WebSocket binary messages."""

import re
import struct
from dataclasses import dataclass

ARTIFACT_HEADER_SIZE = 24
MAX_ARTIFACT_CHUNK_SIZE = 65_536
_HEADER = struct.Struct("!16sQ")
_ID = re.compile(r"[0-9a-f]{32}", re.ASCII)


@dataclass(frozen=True)
class ArtifactChunk:
    transfer_id: str
    offset: int
    payload: bytes


def encode_artifact_chunk(transfer_id: str, offset: int, payload: bytes) -> bytes:
    """Encode 16 ID bytes, uint64 big-endian offset, and 1..65536 payload bytes.

    Offsets describe byte positions within an artifact. Receivers validate the
    next expected offset and descriptor size; this helper validates wire bounds.
    """
    if not isinstance(transfer_id, str) or _ID.fullmatch(transfer_id) is None:
        raise ValueError("Transfer ID must be 32 lowercase hexadecimal digits")
    if type(offset) is not int or not 0 <= offset <= 2**64 - 1:
        raise ValueError("Offset must be an unsigned 64-bit integer")
    if (
        not isinstance(payload, bytes)
        or not 1 <= len(payload) <= MAX_ARTIFACT_CHUNK_SIZE
    ):
        raise ValueError("Payload must contain 1..65536 bytes")
    return _HEADER.pack(bytes.fromhex(transfer_id), offset) + payload


def decode_artifact_chunk(data: bytes) -> ArtifactChunk:
    """Decode one entire binary message, rejecting invalid size with ValueError."""
    if not isinstance(data, bytes) or not (
        ARTIFACT_HEADER_SIZE
        < len(data)
        <= ARTIFACT_HEADER_SIZE + MAX_ARTIFACT_CHUNK_SIZE
    ):
        raise ValueError(
            "Artifact chunk must contain a 24-byte header and 1..65536 bytes"
        )
    identifier, offset = _HEADER.unpack_from(data)
    return ArtifactChunk(identifier.hex(), offset, data[ARTIFACT_HEADER_SIZE:])
