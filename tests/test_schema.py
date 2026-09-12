import json

import pytest
from pydantic import TypeAdapter
from pydantic.json_schema import JsonSchemaMode

from tyvrana_protocol import Message


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_message_union_has_a_portable_json_schema(mode: JsonSchemaMode) -> None:
    schema = TypeAdapter(Message).json_schema(mode=mode)
    assert json.loads(json.dumps(schema)) == schema
    assert schema["discriminator"]["propertyName"] == "type"
    expected = {
        "artifact.begin": "ArtifactBegin",
        "artifact.ready": "ArtifactReady",
        "artifact.complete": "ArtifactComplete",
        "artifact.accepted": "ArtifactAccepted",
        "artifact.abort": "ArtifactAbort",
        "adapter.register": "AdapterRegistration",
        "operation.request": "OperationRequest",
        "operation.success": "OperationSuccess",
        "operation.failure": "OperationFailure",
        "adapter.event": "AdapterEvent",
        "operation.cancel": "CancelRequest",
    }
    assert schema["discriminator"]["mapping"] == {
        tag: f"#/$defs/{name}" for tag, name in expected.items()
    }
    assert {item["$ref"] for item in schema["oneOf"]} == {
        f"#/$defs/{name}" for name in expected.values()
    }
    for tag, name in expected.items():
        model = schema["$defs"][name]
        assert model["additionalProperties"] is False
        assert "type" in model["required"]
        assert model["properties"]["type"]["const"] == tag
    assert schema["$defs"]["ProtocolError"]["additionalProperties"] is False
    operations = schema["$defs"]["AdapterRegistration"]["properties"]["operations"]
    assert operations["type"] == "array"
    assert operations["uniqueItems"] is True
    json_types = schema["$defs"]["JsonValue"]["anyOf"]
    assert {item["type"] for item in json_types} == {
        "null",
        "boolean",
        "integer",
        "number",
        "string",
        "array",
        "object",
    }


def test_response_schema_requires_result_or_error_exclusively() -> None:
    definitions = TypeAdapter(Message).json_schema()["$defs"]
    success = definitions["OperationSuccess"]
    failure = definitions["OperationFailure"]
    assert "result" in success["required"]
    assert "error" not in success["properties"]
    assert "error" in failure["required"]
    assert "result" not in failure["properties"]
