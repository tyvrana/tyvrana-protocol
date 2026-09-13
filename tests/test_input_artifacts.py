import hashlib
import json

import pytest
from pydantic import TypeAdapter, ValidationError

from tyvrana_protocol import (
    ArtifactAccepted,
    ArtifactBegin,
    ArtifactComplete,
    ArtifactDescriptor,
    ArtifactReady,
    Message,
    OperationRequest,
    OperationSuccess,
    decode_artifact_chunk,
    decode_message,
    encode_artifact_chunk,
    encode_message,
)


def descriptor(number: int = 1) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        artifact_id=f"{number:032x}",
        name="texture.png",
        media_type="image/png",
        byte_size=3,
        sha256=hashlib.sha256(b"png").hexdigest(),
    )


@pytest.mark.parametrize("count", [0, 1, 2, 8])
def test_input_attachments_roundtrip(count: int) -> None:
    attachments = tuple(descriptor(i) for i in range(count))
    request = OperationRequest(
        type="operation.request",
        request_id="request-1",
        operation="asset.import",
        arguments={"label": "texture"},
        artifacts=attachments,
    )
    wire = encode_message(request)
    decoded = decode_message(wire)
    assert decoded == request
    assert ("artifacts" in json.loads(wire)) == bool(count)
    assert OperationRequest.model_validate(json.loads(wire)) == request
    assert request.arguments == {"label": "texture"}
    assert isinstance(request.artifacts, tuple)


@pytest.mark.parametrize(
    "attachments",
    [
        None,
        "artifact",
        {},
        ["artifact"],
        [descriptor(), descriptor()],
        [descriptor(), descriptor().model_copy(update={"name": "different.png"})],
        [descriptor(i) for i in range(9)],
        [descriptor().model_dump() | {"path": "texture.png"}],
        [descriptor().model_dump() | {"byte_size": "3"}],
    ],
)
def test_invalid_input_attachments(attachments: object) -> None:
    with pytest.raises(ValidationError):
        OperationRequest.model_validate(
            {
                "type": "operation.request",
                "request_id": "request-1",
                "operation": "asset.import",
                "arguments": {},
                "artifacts": attachments,
            }
        )


def test_request_without_artifacts_and_extra_fields() -> None:
    fields = {
        "type": "operation.request",
        "request_id": "request-1",
        "operation": "scene.inspect",
        "arguments": None,
    }
    request = OperationRequest.model_validate(fields)
    assert request.artifacts == ()
    assert json.loads(encode_message(request)) == fields
    for field in ("artifact_ids", "path", "payload"):
        with pytest.raises(ValidationError):
            OperationRequest.model_validate(fields | {field: "value"})


@pytest.mark.parametrize("inputs", [True, False])
def test_same_controls_and_framing_in_both_directions(inputs: bool) -> None:
    artifact = descriptor()
    transfer = "f" * 32
    controls: list[Message] = [
        ArtifactBegin(
            type="artifact.begin",
            transfer_id=transfer,
            request_id="request-1",
            descriptor=artifact,
        ),
        ArtifactReady(type="artifact.ready", transfer_id=transfer),
        ArtifactComplete(type="artifact.complete", transfer_id=transfer),
        ArtifactAccepted(type="artifact.accepted", transfer_id=transfer),
    ]
    attachment_message: Message
    if inputs:
        attachment_message = OperationRequest(
            type="operation.request",
            request_id="request-1",
            operation="asset.import",
            arguments={},
            artifacts=(artifact,),
        )
    else:
        attachment_message = OperationSuccess(
            type="operation.success",
            request_id="request-1",
            result={},
            artifacts=(artifact,),
        )
    for message in [*controls, attachment_message]:
        assert decode_message(encode_message(message)) == message
    chunk = decode_artifact_chunk(encode_artifact_chunk(transfer, 0, b"png"))
    assert chunk.transfer_id == transfer and chunk.offset == 0
    assert hashlib.sha256(chunk.payload).hexdigest() == artifact.sha256


def test_input_attachment_schema_uses_canonical_descriptor() -> None:
    schema = TypeAdapter(Message).json_schema()
    request = schema["$defs"]["OperationRequest"]
    attachments = request["properties"]["artifacts"]
    assert attachments["type"] == "array"
    assert attachments["maxItems"] == 8
    assert attachments["uniqueItems"] is True
    assert attachments["items"] == {"$ref": "#/$defs/ArtifactDescriptor"}
    assert "artifacts" not in request["required"]
    assert request["additionalProperties"] is False
    assert schema["$defs"]["ArtifactDescriptor"]["additionalProperties"] is False


def test_repeated_artifact_across_requests_uses_immutable_metadata() -> None:
    artifact = descriptor()
    requests = [
        OperationRequest(
            type="operation.request",
            request_id=f"request-{i}",
            operation="asset.import",
            arguments={},
            artifacts=(artifact,),
        )
        for i in range(2)
    ]
    assert requests[0].artifacts == requests[1].artifacts
    with pytest.raises(ValidationError):
        requests[0].artifacts = ()  # type: ignore[misc]
