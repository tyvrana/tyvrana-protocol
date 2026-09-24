"""Proof capability identity cannot be confused with a normal editor registration."""

import pytest
from pydantic import ValidationError

from tyvrana_protocol import AdapterRuntime, ProofArtifact, ProofHostStart, ProofLease


@pytest.mark.parametrize(
    "role,background,leased",
    [("work", False, True), ("proof", False, True), ("proof", True, False)],
)
def test_invalid_process_roles(role: str, background: bool, leased: bool) -> None:
    data = dict(
        role=role,
        background=background,
        build="a" * 64,
        process_id=1,
        proof_lease=dict(lease_id="lease", token="b" * 64, parent_adapter_id="parent")
        if leased
        else None,
    )
    with pytest.raises(ValidationError):
        AdapterRuntime.model_validate(data)


@pytest.mark.parametrize("ttl", [0, 901])
def test_proof_lifetime_is_bounded(ttl: int) -> None:
    with pytest.raises(ValidationError):
        ProofHostStart(
            lease=ProofLease(
                lease_id="lease", token="b" * 64, parent_adapter_id="parent"
            ),
            artifact=ProofArtifact(
                locator="/trusted.asset", sha256="c" * 64, project_id="doc"
            ),
            expected_build="a" * 64,
            ttl_seconds=ttl,
        )
