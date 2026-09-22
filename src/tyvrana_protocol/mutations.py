"""Guarded application mutations and observable, content-qualified receipts."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .attestation import DocumentAttestation
from .messages import ProtocolError, _ProtocolModel
from .resources import ResourceReference, ResourceToken
from .types import JsonValue, QualifiedName


class DocumentMutationRequest(_ProtocolModel):
    mutation_id: ResourceToken
    operation: QualifiedName
    arguments: JsonValue
    host_session_id: ResourceToken
    document_session_id: ResourceToken
    project_id: ResourceToken
    format: Annotated[str, Field(min_length=1, max_length=128)]
    digest: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    resources: list[ResourceReference] = Field(default_factory=list, max_length=4096)


class DocumentMutationResult(_ProtocolModel):
    mutation_id: ResourceToken
    result: JsonValue
    before: DocumentAttestation
    after: DocumentAttestation

    @model_validator(mode="after")
    def qualified(self) -> "DocumentMutationResult":
        if any(e.status != "complete" for e in (self.before, self.after)):
            raise ValueError("Mutation receipts require complete evidence")
        if not self.before.resource_scope or any(
            getattr(self.before, key) != getattr(self.after, key)
            for key in (
                "host_session_id",
                "document_session_id",
                "project_id",
                "format",
                "resource_scope",
            )
        ):
            raise ValueError(
                "Mutation receipts must preserve document identity and scope"
            )
        return self


class DocumentMutationJob(_ProtocolModel):
    job_id: ResourceToken
    state: Literal["queued", "running", "completed", "failed", "cancelled"]
    revision: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    poll_after_seconds: float = Field(default=0.5, ge=0.1, le=5)
    progress: dict[str, JsonValue] | None = None
    result: DocumentMutationResult | None = None
    error: ProtocolError | None = None

    @model_validator(mode="after")
    def terminal_receipt(self) -> "DocumentMutationJob":
        if (self.state == "completed") != (self.result is not None):
            raise ValueError("Only completed mutations require a receipt")
        if self.result and self.result.mutation_id != self.job_id:
            raise ValueError("Mutation receipt must match its job")
        if self.result and self.error:
            raise ValueError("Completed mutations cannot carry an error")
        return self
