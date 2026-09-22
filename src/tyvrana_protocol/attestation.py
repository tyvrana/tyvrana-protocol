"""Compact application-owned evidence for durable document continuity."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .messages import _ProtocolModel
from .resources import ResourceToken


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

    @model_validator(mode="after")
    def qualified(self) -> "DocumentAttestation":
        if self.status == "complete":
            if self.digest is None or self.omissions:
                raise ValueError("Complete evidence requires a digest and no omissions")
        elif self.digest is not None or not self.omissions:
            raise ValueError(
                "Incomplete evidence must explain omissions, without digest"
            )
        return self
