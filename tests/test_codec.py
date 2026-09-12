import json

import pytest
from pydantic import ValidationError

from tyvrana_protocol import (
    AdapterEvent,
    AdapterRegistration,
    CancelRequest,
    JsonValue,
    Message,
    OperationFailure,
    OperationRequest,
    OperationSuccess,
    ProtocolError,
    decode_message,
    encode_message,
)


@pytest.mark.parametrize(
    ("message", "wire"),
    [
        (
            AdapterRegistration(
                type="adapter.register",
                instance_id="adapter-a",
                application="Example Editor",
                application_version="2026.9",
                project_path="projects/example.project",
                operations=("document.inspect",),
            ),
            b'{"application":"Example Editor","application_version":"2026.9",'
            b'"instance_id":"adapter-a","operations":["document.inspect"],'
            b'"project_path":"projects/example.project","type":"adapter.register"}',
        ),
        (
            OperationRequest(
                type="operation.request",
                request_id="request-1",
                operation="document.inspect",
                arguments={},
            ),
            b'{"arguments":{},"operation":"document.inspect",'
            b'"request_id":"request-1","type":"operation.request"}',
        ),
        (
            OperationSuccess(
                type="operation.success", request_id="request-1", result={}
            ),
            b'{"request_id":"request-1","result":{},"type":"operation.success"}',
        ),
        (
            OperationFailure(
                type="operation.failure",
                request_id="request-1",
                error=ProtocolError(
                    code="operation_failed",
                    message="Could not inspect document",
                    details={"retry_possible": False},
                ),
            ),
            b'{"error":{"code":"operation_failed","details":{"retry_possible":false},'
            b'"message":"Could not inspect document"},"request_id":"request-1",'
            b'"type":"operation.failure"}',
        ),
        (
            AdapterEvent(
                type="adapter.event", event="document.changed", payload={"items": 2}
            ),
            b'{"event":"document.changed","payload":{"items":2},"type":"adapter.event"}',
        ),
        (
            CancelRequest(type="operation.cancel", request_id="request-1"),
            b'{"request_id":"request-1","type":"operation.cancel"}',
        ),
    ],
)
def test_all_message_variants_have_exact_round_trips(
    message: Message, wire: bytes
) -> None:
    assert encode_message(message) == wire
    decoded = decode_message(wire)
    assert type(decoded) is type(message)
    assert decoded == message
    assert encode_message(decoded) == wire


@pytest.mark.parametrize("value", [None, {}, [], True, 42, 2.5, "text"])
def test_payloads_allow_all_json_value_shapes(value: JsonValue) -> None:
    messages: list[Message] = [
        OperationRequest(
            type="operation.request",
            request_id="request-1",
            operation="document.inspect",
            arguments=value,
        ),
        OperationSuccess(
            type="operation.success", request_id="request-1", result=value
        ),
        AdapterEvent(type="adapter.event", event="document.changed", payload=value),
    ]
    for message in messages:
        assert decode_message(encode_message(message)) == message


def test_recursive_payloads_and_error_details() -> None:
    value: JsonValue = {
        "items": [None, True, 3, 2.5, "текст", {"nested": [{"empty": {}}, []]}],
        "🌍": "🌍",
        "empty": {},
    }
    messages: list[Message] = [
        OperationRequest(
            type="operation.request",
            request_id="request-1",
            operation="document.inspect",
            arguments=value,
        ),
        OperationSuccess(
            type="operation.success", request_id="request-1", result=value
        ),
        AdapterEvent(type="adapter.event", event="document.changed", payload=value),
        OperationFailure(
            type="operation.failure",
            request_id="request-1",
            error=ProtocolError(code="custom.error", message="Failure", details=value),
        ),
    ]
    for message in messages:
        wire = encode_message(message)
        assert "текст".encode() in wire
        assert decode_message(wire) == message


def test_absent_registration_metadata_is_omitted() -> None:
    registration = AdapterRegistration(
        type="adapter.register",
        instance_id="adapter-a",
        application="Example",
        operations=(),
    )
    wire = encode_message(registration)
    assert wire == (
        b'{"application":"Example","instance_id":"adapter-a",'
        b'"operations":[],"type":"adapter.register"}'
    )
    assert decode_message(wire) == registration


def test_optional_null_metadata_is_normalized_to_absence() -> None:
    decoded = decode_message(
        b'{"type":"adapter.register","instance_id":"adapter-a","application":"Example",'
        b'"operations":[],"application_version":null,"project_path":null}'
    )
    assert b"null" not in encode_message(decoded)


def test_optional_error_details_are_omitted_but_payload_nulls_remain() -> None:
    failure = OperationFailure(
        type="operation.failure",
        request_id="request-1",
        error=ProtocolError(code="failed", message="Failure"),
    )
    assert json.loads(encode_message(failure))["error"] == {
        "code": "failed",
        "message": "Failure",
    }
    success = OperationSuccess(
        type="operation.success", request_id="request-1", result=None
    )
    assert encode_message(success) == (
        b'{"request_id":"request-1","result":null,"type":"operation.success"}'
    )
    nested = AdapterEvent(
        type="adapter.event", event="document.changed", payload={"x": None}
    )
    assert json.loads(encode_message(nested))["payload"] == {"x": None}


def test_encoding_is_independent_of_nested_object_insertion_order() -> None:
    first = OperationSuccess(
        type="operation.success",
        request_id="request-1",
        result={"z": {"b": 2, "a": 1}, "a": 0},
    )
    second = OperationSuccess(
        type="operation.success",
        request_id="request-1",
        result={"a": 0, "z": {"a": 1, "b": 2}},
    )
    assert encode_message(first) == encode_message(second)


@pytest.mark.parametrize(
    "data",
    [
        {},
        [],
        None,
        {"type": "unknown"},
        {"type": 1},
        {"type": "operation.request", "operation": "document.inspect", "arguments": {}},
        {"type": "operation.request", "request_id": "r", "arguments": {}},
        {
            "type": "operation.request",
            "request_id": "r",
            "operation": "document.inspect",
        },
        {"type": "operation.cancel", "request_id": 1},
        {"type": "operation.cancel", "request_id": " "},
        {"type": "operation.success", "request_id": "r"},
        {"type": "operation.failure", "request_id": "r"},
        {"type": "operation.failure", "request_id": "r", "error": None},
        {"type": "adapter.event", "event": "document.changed"},
        {"type": "adapter.event", "event": "changed", "payload": {}},
        {"type": "adapter.register", "instance_id": "a", "application": "Example"},
    ],
)
def test_malformed_message_structures_are_rejected(data: object) -> None:
    with pytest.raises(ValidationError):
        decode_message(json.dumps(data).encode())


@pytest.mark.parametrize(
    "data",
    [
        {
            "type": "adapter.register",
            "instance_id": "a",
            "application": "App",
            "operations": [],
        },
        {
            "type": "operation.request",
            "request_id": "r",
            "operation": "a.b",
            "arguments": {},
        },
        {"type": "operation.success", "request_id": "r", "result": {}},
        {
            "type": "operation.failure",
            "request_id": "r",
            "error": {"code": "failed", "message": "Failure"},
        },
        {"type": "adapter.event", "event": "a.b", "payload": {}},
        {"type": "operation.cancel", "request_id": "r"},
    ],
)
def test_all_message_variants_reject_extra_fields(data: dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        decode_message(json.dumps({**data, "unexpected": True}).encode())


def test_structured_error_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        decode_message(
            b'{"type":"operation.failure","request_id":"r",'
            b'"error":{"code":"failed","message":"Failure","unexpected":true}}'
        )


@pytest.mark.parametrize(
    "data",
    [
        {
            "type": "operation.success",
            "request_id": "r",
            "result": None,
            "error": {"code": "failed", "message": "Failure"},
        },
        {
            "type": "operation.failure",
            "request_id": "r",
            "result": {},
            "error": {"code": "failed", "message": "Failure"},
        },
    ],
)
def test_responses_cannot_mix_success_and_failure(data: dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        decode_message(json.dumps(data).encode())


@pytest.mark.parametrize(
    "wire",
    [
        b"",
        b"{",
        b'[{"type":"operation.cancel","request_id":"r"}]',
        b'{"type":"operation.cancel","request_id":"r",}',
        b'{"type":"operation.cancel","request_id":"r"} trailing',
        b'{"type":"operation.cancel","request_id":"\xff"}',
        '{"type":"operation.cancel","request_id":"r"}'.encode("utf-16"),
        b'{"type":"operation.cancel","type":"operation.cancel","request_id":"r"}',
        b'{"type":"operation.success","request_id":"r","result":{"x":1,"x":2}}',
        b'{"type":"operation.success","request_id":"r","result":"\\ud800"}',
        b'{"type":"operation.success","request_id":"r","result":{"\\udfff":null}}',
    ],
)
def test_invalid_json_and_duplicate_keys_are_rejected(wire: bytes) -> None:
    with pytest.raises(ValueError):
        decode_message(wire)


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_non_finite_wire_numbers_are_rejected(number: str) -> None:
    wire = f'{{"type":"operation.success","request_id":"r","result":{number}}}'.encode()
    with pytest.raises(ValidationError):
        decode_message(wire)


def test_encoder_revalidates_changed_json_containers() -> None:
    message = OperationSuccess(
        type="operation.success", request_id="r", result={"x": 1}
    )
    assert isinstance(message.result, dict)
    message.result["x"] = float("nan")
    with pytest.raises(ValidationError):
        encode_message(message)


def test_encoder_rejects_validation_bypassing_model_copy() -> None:
    message = CancelRequest(type="operation.cancel", request_id="r")
    invalid = message.model_copy(update={"request_id": 123})
    with pytest.raises(ValidationError):
        encode_message(invalid)


def test_nested_errors_are_revalidated() -> None:
    error = ProtocolError.model_construct(code="", message="Failure")
    with pytest.raises(ValidationError):
        OperationFailure(type="operation.failure", request_id="r", error=error)
