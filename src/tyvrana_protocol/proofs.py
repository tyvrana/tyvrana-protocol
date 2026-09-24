"""Application-owned disposable hosts for independent durable-artifact proof."""

from typing import Annotated, Literal

from pydantic import Field

from .messages import ProofLease, ProtocolError, _ProtocolModel
from .types import Identifier


class ProofArtifact(_ProtocolModel):
    """Locator is reopening information; SHA and project identity are authority."""

    locator: str = Field(min_length=1, max_length=4096)
    sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    project_id: Identifier


class ProofHostStart(_ProtocolModel):
    lease: ProofLease
    artifact: ProofArtifact
    expected_build: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    ttl_seconds: int = Field(ge=1, le=900)


class ProofHostControl(_ProtocolModel):
    lease: ProofLease


class ProofHostStatus(_ProtocolModel):
    lease_id: Identifier
    state: Literal["starting", "ready", "failed", "stopped"]
    process_id: int | None = Field(default=None, gt=0)
    error: ProtocolError | None = None
