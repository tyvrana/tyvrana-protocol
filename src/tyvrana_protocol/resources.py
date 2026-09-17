"""Portable, bounded identity inspection for semantic application bindings."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .messages import _ProtocolModel
from .types import Identifier

type ResourceToken = Annotated[Identifier, Field(max_length=128)]


class ResourceReference(_ProtocolModel):
    """Adapter-defined resource kind and saved opaque identity, never a name."""

    resource_kind: ResourceToken
    resource_id: ResourceToken


class ResourceInspectionRequest(_ProtocolModel):
    """Resolve identities only in the expected saved application document."""

    project_id: ResourceToken
    resources: list[ResourceReference] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_resources(self) -> "ResourceInspectionRequest":
        keys = [(r.resource_kind, r.resource_id) for r in self.resources]
        if len(set(keys)) != len(keys):
            raise ValueError("Resource references must be unique")
        return self


class ResourceObservation(ResourceReference):
    """Existence is not content validation; fingerprints cover declared scope only."""

    state: Literal["present", "missing", "ambiguous", "unsupported"]
    name: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    fingerprint: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class ResourceInspectionResult(_ProtocolModel):
    project_id: ResourceToken
    resources: list[ResourceObservation] = Field(min_length=1, max_length=64)
    fingerprint_scope: Annotated[str, Field(min_length=1, max_length=512)]
