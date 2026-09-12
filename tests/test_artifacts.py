import hashlib
import json

import pytest
from pydantic import ValidationError

from tyvrana_protocol import (
    ARTIFACT_HEADER_SIZE,
    MAX_ARTIFACT_CHUNK_SIZE,
    ArtifactAbort,
    ArtifactAccepted,
    ArtifactBegin,
    ArtifactComplete,
    ArtifactDescriptor,
    ArtifactReady,
    Message,
    OperationSuccess,
    ProtocolError,
    decode_artifact_chunk,
    decode_message,
    encode_artifact_chunk,
    encode_message,
)

ID = "00112233445566778899aabbccddeeff"
DESCRIPTOR = ArtifactDescriptor(
    artifact_id=ID,
    media_type="image/png",
    byte_size=3,
    sha256=hashlib.sha256(b"png").hexdigest(),
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_id", "../image"),
        ("artifact_id", ID.upper()),
        ("artifact_id", ID + "\n"),
        ("artifact_id", 42),
        ("name", ""),
        ("name", "  "),
        ("name", "x" * 256),
        ("media_type", "image"),
        ("media_type", "Image/PNG"),
        ("media_type", "image/png; charset=utf-8"),
        ("media_type", "image/png\n"),
        ("media_type", "a/" + "b" * 126),
        ("byte_size", -1),
        ("byte_size", 2**53),
        ("byte_size", True),
        ("byte_size", "3"),
        ("byte_size", 3.0),
        ("sha256", "0" * 63),
        ("sha256", "A" * 64),
        ("sha256", "0" * 64 + "\n"),
        ("path", "/tmp/render.png"),
        ("metadata", {}),
    ],
)
def test_invalid_descriptor(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ArtifactDescriptor.model_validate(DESCRIPTOR.model_dump() | {field: value})


def test_descriptor_zero_bytes_optional_name_and_frozen_fields() -> None:
    descriptor = ArtifactDescriptor(
        artifact_id=ID,
        name=None,
        media_type="application/octet-stream",
        byte_size=0,
        sha256=hashlib.sha256(b"").hexdigest(),
    )
    assert "name" not in descriptor.model_dump()
    with pytest.raises(ValidationError):
        descriptor.name = "changed"  # type: ignore[misc]
    assert (
        ArtifactDescriptor.model_validate(
            descriptor.model_dump() | {"name": "render.png"}
        ).name
        == "render.png"
    )


@pytest.mark.parametrize(
    "message",
    [
        ArtifactBegin(
            type="artifact.begin",
            transfer_id=ID,
            request_id="request-1",
            descriptor=DESCRIPTOR,
        ),
        ArtifactReady(type="artifact.ready", transfer_id=ID),
        ArtifactComplete(type="artifact.complete", transfer_id=ID),
        ArtifactAccepted(type="artifact.accepted", transfer_id=ID),
        ArtifactAbort(
            type="artifact.abort",
            transfer_id=ID,
            error=ProtocolError(code="transfer_failed", message="Invalid hash"),
        ),
    ],
)
def test_control_roundtrip_and_strict_fields(message: Message) -> None:
    wire = encode_message(message)
    assert decode_message(wire) == message
    for change in ({"extra": True}, {"transfer_id": "bad"}):
        with pytest.raises(ValueError):
            decode_message(json.dumps(json.loads(wire) | change).encode())


@pytest.mark.parametrize("count", [0, 1, 2, 8])
def test_success_artifacts(count: int) -> None:
    artifacts = tuple(
        DESCRIPTOR.model_copy(update={"artifact_id": f"{i:032x}"}) for i in range(count)
    )
    message = OperationSuccess(
        type="operation.success", request_id="r", result=None, artifacts=artifacts
    )
    wire = encode_message(message)
    assert decode_message(wire) == message
    assert ("artifacts" in json.loads(wire)) == bool(count)


@pytest.mark.parametrize(
    "artifacts", [[DESCRIPTOR, DESCRIPTOR], [DESCRIPTOR] * 9, None]
)
def test_invalid_result_artifacts(artifacts: object) -> None:
    with pytest.raises(ValidationError):
        OperationSuccess.model_validate(
            dict(
                type="operation.success", request_id="r", result={}, artifacts=artifacts
            )
        )


def test_exact_binary_layout() -> None:
    wire = encode_artifact_chunk(ID, 0x0102030405060708, b"\x00\xffPNG")
    assert ARTIFACT_HEADER_SIZE == 24
    assert wire == bytes.fromhex(ID + "0102030405060708") + b"\x00\xffPNG"
    chunk = decode_artifact_chunk(wire)
    assert (chunk.transfer_id, chunk.offset, chunk.payload) == (
        ID,
        0x0102030405060708,
        b"\x00\xffPNG",
    )


@pytest.mark.parametrize("offset", [0, 1, 2**64 - 1])
@pytest.mark.parametrize("size", [1, MAX_ARTIFACT_CHUNK_SIZE])
def test_binary_bounds(offset: int, size: int) -> None:
    payload = b"x" * size
    assert (
        decode_artifact_chunk(encode_artifact_chunk(ID, offset, payload)).payload
        == payload
    )


@pytest.mark.parametrize(
    "size", [0, 1, 15, 16, 23, 24, ARTIFACT_HEADER_SIZE + MAX_ARTIFACT_CHUNK_SIZE + 1]
)
def test_invalid_binary_length(size: int) -> None:
    with pytest.raises(ValueError):
        decode_artifact_chunk(b"x" * size)


@pytest.mark.parametrize("identifier", ["", "bad", ID.upper(), ID + "\n", "g" * 32])
def test_invalid_binary_id(identifier: str) -> None:
    with pytest.raises(ValueError):
        encode_artifact_chunk(identifier, 0, b"x")


@pytest.mark.parametrize("offset", [-1, 2**64, True, 1.5, "0"])
def test_invalid_binary_offset(offset: object) -> None:
    with pytest.raises(ValueError):
        encode_artifact_chunk(ID, offset, b"x")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload", [b"", b"x" * (MAX_ARTIFACT_CHUNK_SIZE + 1), "x", bytearray(b"x")]
)
def test_invalid_binary_payload(payload: object) -> None:
    with pytest.raises(ValueError):
        encode_artifact_chunk(ID, 0, payload)  # type: ignore[arg-type]
