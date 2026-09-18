from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from tyvrana_protocol import (
    AdapterRegistration,
    JsonValue,
    OperationContract,
    OperationRequest,
    ProtocolError,
    QualifiedName,
    encode_message,
)


@pytest.mark.parametrize("operations", [[], ["document.inspect", "asset.describe"]])
def test_registration_accepts_json_operation_arrays(operations: list[str]) -> None:
    registration = AdapterRegistration.model_validate(
        {
            "type": "adapter.register",
            "instance_id": "adapter-a",
            "application": "A Future Application",
            "operations": [contract(name).model_dump() for name in operations],
        }
    )
    assert registration.operation_names == tuple(operations)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("instance_id", ""),
        ("instance_id", "has spaces"),
        ("instance_id", 123),
        ("application", ""),
        ("application", "  \t"),
        ("application", True),
        ("application_version", ""),
        ("application_version", 5.2),
        ("project_path", ""),
        ("project_path", Path("project.file")),
        ("operations", "document.inspect"),
        ("operations", {"document.inspect"}),
        ("operations", ["document.inspect", "document.inspect"]),
        ("operations", ["Document.inspect"]),
        ("operations", ["inspect"]),
        ("operations", [123]),
    ],
)
def test_invalid_registration_is_rejected(field: str, value: object) -> None:
    data: dict[str, object] = {
        "type": "adapter.register",
        "instance_id": "adapter-a",
        "application": "Example Editor",
        "operations": [],
    }
    data[field] = value
    with pytest.raises(ValidationError):
        AdapterRegistration.model_validate(data)


@pytest.mark.parametrize(
    "name", ["document.inspect", "asset.mesh.inspect", "custom_tool.action_2"]
)
def test_qualified_names(name: str) -> None:
    assert TypeAdapter(QualifiedName).validate_python(name) == name


@pytest.mark.parametrize(
    "name", ["", "inspect", ".inspect", "document.", "a..b", "A.b", "a.2b", "a.b\n"]
)
def test_invalid_names(name: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(QualifiedName).validate_python(name)


@pytest.mark.parametrize(
    "value",
    [
        object(),
        b"bytes",
        Decimal("1.25"),
        Path("asset.file"),
        (1, 2),
        {1, 2},
        {1: "non-string key"},
        {"nested": [b"bytes"]},
        "\ud800",
        {"\udfff": None},
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_json_values_reject_non_json_python_data(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(JsonValue).validate_python(value)


@pytest.mark.parametrize("value", [None, True, False, 0, -2, 1.25, "text", [], {}])
def test_json_values_preserve_scalar_and_container_types(value: JsonValue) -> None:
    result = TypeAdapter[JsonValue](JsonValue).validate_python(value)
    assert result == value
    assert type(result) is type(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [("code", ""), ("code", "has spaces"), ("message", ""), ("message", "  ")],
)
def test_invalid_error_fields(field: str, value: str) -> None:
    data = {"code": "operation_failed", "message": "Operation failed"}
    data[field] = value
    with pytest.raises(ValidationError):
        ProtocolError.model_validate(data)


def test_models_are_frozen() -> None:
    request = OperationRequest(
        type="operation.request",
        request_id="request-1",
        operation="document.inspect",
        arguments={},
    )
    with pytest.raises(ValidationError, match="frozen"):
        request.operation = "document.change"  # type: ignore[misc]


def test_validation_copies_nested_payload_containers() -> None:
    items: list[JsonValue] = [1]
    arguments: dict[str, JsonValue] = {"items": items}
    request = OperationRequest(
        type="operation.request",
        request_id="request-1",
        operation="document.inspect",
        arguments=arguments,
    )
    original_wire = encode_message(request)
    items.append(2)
    arguments["new"] = True
    assert encode_message(request) == original_wire


def test_registration_does_not_retain_the_input_operation_list() -> None:
    operations = ["document.inspect"]
    registration = AdapterRegistration.model_validate(
        {
            "type": "adapter.register",
            "instance_id": "adapter-a",
            "application": "Example Editor",
            "operations": [contract(name).model_dump() for name in operations],
        }
    )
    operations.append("asset.describe")
    assert registration.operation_names == ("document.inspect",)


def contract(name: str = "document.inspect") -> OperationContract:
    return OperationContract(
        name=name,
        description="Inspect a document.",
        arguments_schema={"type": "object"},
        result_schema={"type": "object"},
        effect="read_only",
        execution="synchronous",
    )


def test_duplicate_contract_names_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        AdapterRegistration(
            type="adapter.register",
            instance_id="a",
            application="Test",
            operations=(contract(), contract()),
        )


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": "https://example.com/schema"},
        {"$defs": {"nested": {"$dynamicRef": "external.json"}}},
        {"description": "x" * 131072},
    ],
)
def test_invalid_contract_schema_is_rejected(schema: dict[str, JsonValue]) -> None:
    data = contract().model_dump()
    data["arguments_schema"] = schema
    with pytest.raises(ValidationError):
        OperationContract.model_validate(data)


def test_contract_schemas_preserve_constraints_and_copy_inputs() -> None:
    schema: dict[str, JsonValue] = {
        "$defs": {"N": {"type": "integer", "minimum": 1}},
        "type": "object",
        "properties": {"count": {"$ref": "#/$defs/N"}},
        "required": ["count"],
        "additionalProperties": False,
    }
    data = contract().model_dump()
    data["arguments_schema"] = schema
    c = OperationContract.model_validate(data)
    schema["required"] = []
    assert c.arguments_schema["required"] == ["count"]
    assert OperationContract.model_validate_json(c.model_dump_json()) == c


@pytest.mark.parametrize(
    "changes",
    [
        {"category": ""},
        {"category": "a" * 65},
        {"category": "Unsafe label"},
        {"tags": ["same", "same"]},
        {"tags": ["a" * 49]},
        {"tags": [f"tag{i}" for i in range(13)]},
    ],
)
def test_capability_metadata_bounds(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        OperationContract.model_validate(contract().model_dump() | changes)


def test_capability_metadata_roundtrip() -> None:
    value = OperationContract.model_validate(
        contract().model_dump()
        | {
            "category": "geometry",
            "tags": ["clearance", "sampled"],
        }
    )
    assert value.tags == ("clearance", "sampled")
    assert OperationContract.model_validate_json(value.model_dump_json()) == value
