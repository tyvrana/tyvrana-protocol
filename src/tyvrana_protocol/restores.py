"""Explicit replacement of an observed document by a proven durable artifact."""

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .attestation import DocumentAttestation
from .messages import ProtocolError, _ProtocolModel
from .resources import ResourceToken
from .types import JsonValue, QualifiedName

Digest = Annotated[str, Field(pattern="^[0-9a-f]{64}$")]


class DocumentState(_ProtocolModel):
    host_session_id: ResourceToken
    document_session_id: ResourceToken
    project_id: ResourceToken | None
    format: Annotated[str, Field(min_length=1, max_length=128)]
    digest: Digest


class DocumentRestoreTarget(_ProtocolModel):
    project_id: ResourceToken
    format: Annotated[str, Field(min_length=1, max_length=128)]
    digest: Digest
    file_sha256: Digest


class DocumentRestoreRequest(_ProtocolModel):
    mutation_id: ResourceToken
    operation: QualifiedName
    arguments: JsonValue
    discard_current: Literal[True]
    current: DocumentState
    target: DocumentRestoreTarget

    @field_validator("discard_current", mode="before")
    @classmethod
    def explicit_discard(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Restore requires explicit discard_current: true")
        return value


class DocumentRestoreResult(_ProtocolModel):
    mutation_id: ResourceToken
    result: JsonValue
    before: DocumentAttestation
    after: DocumentAttestation

    @model_validator(mode="after")
    def qualified(self) -> "DocumentRestoreResult":
        if any(e.status != "complete" for e in (self.before, self.after)):
            raise ValueError("Restore receipts require complete evidence")
        if self.before.host_session_id != self.after.host_session_id:
            raise ValueError("Restore must preserve the executing host")
        return self


class DocumentRestoreJob(_ProtocolModel):
    job_id: ResourceToken
    state: Literal["queued", "running", "completed", "failed", "cancelled"]
    revision: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    poll_after_seconds: float = Field(default=0.5, ge=0.1, le=5)
    progress: dict[str, JsonValue] | None = None
    result: DocumentRestoreResult | None = None
    error: ProtocolError | None = None

    @model_validator(mode="after")
    def terminal_receipt(self) -> "DocumentRestoreJob":
        if (self.state == "completed") != (self.result is not None):
            raise ValueError("Only completed restores require a receipt")
        if self.result and (self.result.mutation_id != self.job_id or self.error):
            raise ValueError("Restore receipt correlation or terminal state differs")
        return self
