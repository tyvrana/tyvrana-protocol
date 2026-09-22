"""Compact application-owned evidence for durable document continuity."""

from typing import Annotated, Literal

from pydantic import Field, RootModel, model_validator

from .messages import ProtocolError, _ProtocolModel
from .resources import ResourceToken


class AttestationLimits(_ProtocolModel):
    stream_bytes: int = Field(ge=1)
    stream_items: int = Field(ge=1)
    bulk_elements: int = Field(ge=1)
    buffer_bytes: int = Field(ge=1)
    resources: int = Field(ge=1)
    elapsed_ms: int = Field(ge=1)
    nesting: int = Field(ge=1)
    resource_elapsed_ms: int | None = Field(default=None, ge=1)


class AttestationCost(_ProtocolModel):
    category: str = Field(max_length=64)
    resource: str = Field(default="", max_length=256)
    resources: int = Field(ge=0)
    stream_bytes: int = Field(ge=0)
    stream_items: int = Field(ge=0)
    bulk_elements: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)


class AttestationWork(_ProtocolModel):
    """Bounded counters, never authored arrays or per-component payloads."""

    exceeded: (
        Literal[
            "stream_bytes",
            "stream_items",
            "bulk_elements",
            "buffer_bytes",
            "resources",
            "elapsed_ms",
            "nesting",
            "resource_elapsed_ms",
        ]
        | None
    ) = None
    stream_bytes: int = Field(ge=0)
    stream_items: int = Field(ge=0)
    bulk_elements: int = Field(ge=0)
    resources_completed: int = Field(ge=0)
    peak_buffer_bytes: int = Field(ge=0)
    current_category: str = Field(max_length=64)
    current_resource: str = Field(max_length=256)
    limits: AttestationLimits
    categories: list[AttestationCost] = Field(max_length=32)
    heaviest: list[AttestationCost] = Field(max_length=8)


class DocumentAttestation(_ProtocolModel):
    """Complete means no relevant state was silently omitted by the named format."""

    host_session_id: ResourceToken
    document_session_id: ResourceToken
    project_id: ResourceToken | None
    algorithm: Literal["sha256"] = "sha256"
    format: Annotated[str, Field(min_length=1, max_length=128)]
    digest: Annotated[str, Field(pattern="^[0-9a-f]{64}$")] | None
    status: Literal["complete", "unsupported", "limit_exceeded"]
    resource_count: Annotated[int, Field(ge=0, le=100000)]
    omissions: list[Annotated[str, Field(max_length=256)]] = Field(max_length=32)
    elapsed_ms: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    file_sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")] | None = None

    work: AttestationWork | None = None

    @model_validator(mode="after")
    def qualified(self) -> "DocumentAttestation":
        if self.status == "complete":
            if (
                self.digest is None
                or self.omissions
                or (self.work and self.work.exceeded)
            ):
                raise ValueError("Complete evidence requires a digest and no omissions")
        elif self.digest is not None or not self.omissions:
            raise ValueError(
                "Incomplete evidence must explain omissions, without digest"
            )
        return self


class DocumentAttestationJob(_ProtocolModel):
    """Observable application work with bounded progress and final evidence."""

    job_id: ResourceToken
    state: Literal["queued", "running", "completed", "failed", "cancelled"]
    revision: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    poll_after_seconds: float = Field(default=0.5, ge=0.1, le=5)
    progress: AttestationWork | None = None
    result: DocumentAttestation | None = None
    error: ProtocolError | None = None

    @model_validator(mode="after")
    def terminal_evidence(self) -> "DocumentAttestationJob":
        if self.state == "completed" and self.result is None:
            raise ValueError("Completed attestation job requires evidence")
        if self.state != "completed" and self.result is not None:
            raise ValueError("Only completed jobs may expose evidence")
        return self


class DocumentAttestationResponse(
    RootModel[DocumentAttestation | DocumentAttestationJob]
):
    pass
