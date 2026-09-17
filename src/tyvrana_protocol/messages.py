"""Application-independent messages exchanged by core and running adapters."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .types import ArtifactId, Identifier, JsonValue, QualifiedName, TransferId

type _NonBlankText = Annotated[str, Field(min_length=1, pattern=r"\S")]


class _ProtocolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        revalidate_instances="always",
    )


class ProtocolError(_ProtocolModel):
    """A machine-readable failure with optional application-defined details."""

    code: Identifier
    message: _NonBlankText
    details: JsonValue = Field(default=None, exclude_if=lambda value: value is None)


class OperationContract(_ProtocolModel):
    """Self-contained operation schemas and behavior, supplied by the adapter."""

    name: QualifiedName
    description: Annotated[str, Field(min_length=1, max_length=1600, pattern=r"\S")]
    arguments_schema: dict[str, JsonValue]
    result_schema: dict[str, JsonValue]
    effect: Literal["read_only", "mutating", "transient", "lifecycle"]
    execution: Literal["synchronous", "job_start", "job_status", "lifecycle"]
    requires_interactive: bool = False
    input_artifacts: Literal["none", "required"] = "none"
    output_artifacts: Literal["none", "optional", "required"] = "none"

    @field_validator("arguments_schema", "result_schema")
    @classmethod
    def bounded_local_schema(cls, schema: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if len(json.dumps(schema, ensure_ascii=False).encode("utf-8")) > 131072:
            raise ValueError("Each operation schema is limited to 128 KiB")
        pending: list[JsonValue] = [schema]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                for key in ("$ref", "$dynamicRef"):
                    reference = item.get(key)
                    if key in item and (
                        not isinstance(reference, str) or not reference.startswith("#")
                    ):
                        raise ValueError("Operation schema references must be local")
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
        return schema


class ArtifactDescriptor(_ProtocolModel):
    """Metadata for immutable bytes, never a location or an embedded payload."""

    artifact_id: ArtifactId
    name: Annotated[str, Field(min_length=1, max_length=255, pattern=r"\S")] | None = (
        Field(default=None, exclude_if=lambda value: value is None)
    )
    media_type: Annotated[
        str,
        Field(
            max_length=127,
            pattern=r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$",
        ),
    ]
    byte_size: Annotated[int, Field(ge=0, le=2**53 - 1)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class AdapterRegistration(_ProtocolModel):
    """Identify one running application instance and its supported operations."""

    type: Literal["adapter.register"]
    instance_id: Identifier
    application: _NonBlankText
    application_version: _NonBlankText | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    project_path: _NonBlankText | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    project_id: Annotated[Identifier, Field(max_length=128)] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Saved application-document identity; paths are only locators.",
    )
    resource_inspection: QualifiedName | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description="Advertised read-only ResourceInspectionRequest/Result operation.",
    )
    operations: tuple[OperationContract, ...] = Field(
        max_length=512, json_schema_extra={"uniqueItems": True}
    )

    @field_validator("operations", mode="before")
    @classmethod
    def _accept_json_array(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("operations")
    @classmethod
    def _require_unique_operations(
        cls, value: tuple[OperationContract, ...]
    ) -> tuple[OperationContract, ...]:
        if len(value) != len({item.name for item in value}):
            raise ValueError("Advertised operation names must be unique")
        return value

    @property
    def operation_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.operations)

    @model_validator(mode="after")
    def inspection_is_advertised(self) -> "AdapterRegistration":
        if self.resource_inspection is not None and not any(
            op.name == self.resource_inspection
            and op.effect == "read_only"
            and op.input_artifacts == "none"
            and op.output_artifacts == "none"
            for op in self.operations
        ):
            raise ValueError(
                "Resource inspection must advertise a read-only operation "
                "without artifacts"
            )
        return self


class _ArtifactMessage(_ProtocolModel):
    """An operation's ordered, complete input or output attachments."""

    artifacts: tuple[ArtifactDescriptor, ...] = Field(
        default=(),
        max_length=8,
        exclude_if=lambda value: not value,
        json_schema_extra={"uniqueItems": True},
    )

    @field_validator("artifacts", mode="before")
    @classmethod
    def _accept_artifact_array(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("artifacts")
    @classmethod
    def _unique_artifacts(
        cls, value: tuple[ArtifactDescriptor, ...]
    ) -> tuple[ArtifactDescriptor, ...]:
        if len({item.artifact_id for item in value}) != len(value):
            raise ValueError("Attached artifact identifiers must be unique")
        return value


class OperationRequest(_ArtifactMessage):
    """Perform one operation after its input artifacts have been accepted."""

    type: Literal["operation.request"]
    request_id: Identifier
    operation: QualifiedName
    arguments: JsonValue


class OperationSuccess(_ArtifactMessage):
    """Return a result after its output artifacts have been accepted."""

    type: Literal["operation.success"]
    request_id: Identifier
    result: JsonValue


class OperationFailure(_ProtocolModel):
    """Return a structured failure for an operation request."""

    type: Literal["operation.failure"]
    request_id: Identifier
    error: ProtocolError


class AdapterEvent(_ProtocolModel):
    """Report an unsolicited event from the connected adapter instance."""

    type: Literal["adapter.event"]
    event: QualifiedName
    payload: JsonValue


class CancelRequest(_ProtocolModel):
    """Identify the in-flight operation whose cancellation is requested."""

    type: Literal["operation.cancel"]
    request_id: Identifier


class ArtifactBegin(_ProtocolModel):
    """Sender requests receiver storage for one operation input or output."""

    type: Literal["artifact.begin"]
    transfer_id: TransferId
    request_id: Identifier
    descriptor: ArtifactDescriptor


class ArtifactReady(_ProtocolModel):
    """Receiver reserved storage; the sender may start sending chunks."""

    type: Literal["artifact.ready"]
    transfer_id: TransferId


class ArtifactComplete(_ProtocolModel):
    """Sender sent every byte and requests integrity verification."""

    type: Literal["artifact.complete"]
    transfer_id: TransferId


class ArtifactAccepted(_ProtocolModel):
    """Receiver verified bytes; the operation request/result may reference them."""

    type: Literal["artifact.accepted"]
    transfer_id: TransferId


class ArtifactAbort(_ProtocolModel):
    """Either endpoint terminates a transfer and its related operation."""

    type: Literal["artifact.abort"]
    transfer_id: TransferId
    error: ProtocolError


type Message = Annotated[
    AdapterRegistration
    | OperationRequest
    | OperationSuccess
    | OperationFailure
    | AdapterEvent
    | CancelRequest
    | ArtifactBegin
    | ArtifactReady
    | ArtifactComplete
    | ArtifactAccepted
    | ArtifactAbort,
    Field(discriminator="type"),
]
