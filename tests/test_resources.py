import pytest
from pydantic import ValidationError

from tyvrana_protocol import (
    AdapterRegistration,
    OperationContract,
    ResourceInspectionRequest,
    ResourceInspectionResult,
    decode_message,
    encode_message,
)


def test_saved_identity_and_portable_inspector_roundtrip() -> None:
    operation = OperationContract(
        name="editor.resources.inspect",
        description="Resolve saved resource identities",
        arguments_schema=ResourceInspectionRequest.model_json_schema(),
        result_schema=ResourceInspectionResult.model_json_schema(),
        effect="read_only",
        execution="synchronous",
    )
    registration = AdapterRegistration(
        type="adapter.register",
        instance_id="runtime",
        application="Example",
        project_id="saved-document",
        resource_inspection=operation.name,
        operations=(operation,),
    )
    assert decode_message(encode_message(registration)) == registration
    invalid: list[dict[str, object]] = [
        {"operations": ()},
        {"operations": (operation.model_copy(update={"effect": "mutating"}),)},
    ]
    for changes in invalid:
        with pytest.raises(ValidationError, match="read-only"):
            AdapterRegistration.model_validate({**registration.model_dump(), **changes})


def test_resource_requests_are_bounded_and_unique() -> None:
    resource = {"resource_kind": "asset", "resource_id": "saved-id"}
    data = {"project_id": "document", "resources": [resource]}
    assert (
        ResourceInspectionRequest.model_validate(data).resources[0].resource_id
        == "saved-id"
    )
    for resources in [[], [resource, resource], [resource] * 65]:
        with pytest.raises(ValidationError):
            ResourceInspectionRequest.model_validate({**data, "resources": resources})
    with pytest.raises(ValidationError):
        ResourceInspectionRequest.model_validate({**data, "metadata": {"opaque": True}})
