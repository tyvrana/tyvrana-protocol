"""Application-independent messages exchanged by core and running adapters."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    operations: tuple[QualifiedName, ...] = Field(
        json_schema_extra={"uniqueItems": True}
    )

    @field_validator("operations", mode="before")
    @classmethod
    def _accept_json_array(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("operations")
    @classmethod
    def _require_unique_operations(
        cls, value: tuple[QualifiedName, ...]
    ) -> tuple[QualifiedName, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Advertised operation names must be unique")
        return value


class OperationRequest(_ProtocolModel):
    """Ask an adapter to perform one named operation."""

    type: Literal["operation.request"]
    request_id: Identifier
    operation: QualifiedName
    arguments: JsonValue


class OperationSuccess(_ProtocolModel):
    """Return an operation's result, including a meaningful JSON null."""

    type: Literal["operation.success"]
    request_id: Identifier
    result: JsonValue
    artifacts: tuple[ArtifactDescriptor, ...] = Field(
        default=(), max_length=8, exclude_if=lambda value: not value
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
            raise ValueError("Artifact identifiers must be unique in a result")
        return value


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
    """Adapter requests storage for one artifact of an outstanding operation."""

    type: Literal["artifact.begin"]
    transfer_id: TransferId
    request_id: Identifier
    descriptor: ArtifactDescriptor


class ArtifactReady(_ProtocolModel):
    """Core has reserved storage; the adapter may start sending chunks."""

    type: Literal["artifact.ready"]
    transfer_id: TransferId


class ArtifactComplete(_ProtocolModel):
    """Adapter has sent every byte and requests integrity verification."""

    type: Literal["artifact.complete"]
    transfer_id: TransferId


class ArtifactAccepted(_ProtocolModel):
    """Core verified the bytes; operation success may reference the artifact."""

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
