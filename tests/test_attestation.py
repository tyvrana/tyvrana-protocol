"""Complete content evidence cannot silently omit resources."""

from typing import Any

import pytest
from pydantic import ValidationError

from tyvrana_protocol import DocumentAttestation


def test_complete_attestation_and_incomplete_evidence() -> None:
    value: dict[str, Any] = dict(
        host_session_id="process",
        document_session_id="loaded",
        project_id=None,
        format="editor-material",
        digest="a" * 64,
        status="complete",
        resource_count=8,
        omissions=[],
        elapsed_ms=1.5,
    )
    qualified = DocumentAttestation.model_validate(value)
    assert (
        DocumentAttestation.model_validate_json(qualified.model_dump_json())
        == qualified
    )
    invalid_cases: list[dict[str, Any]] = [
        dict(omissions=["Skipped geometry"]),
        dict(digest=None),
        dict(elapsed_ms=float("nan")),
    ]
    for invalid in invalid_cases:
        with pytest.raises(ValidationError):
            DocumentAttestation.model_validate({**value, **invalid})
    incomplete = DocumentAttestation.model_validate(
        {
            **value,
            "digest": None,
            "status": "unsupported",
            "omissions": ["Unsupported cache"],
        }
    )
    assert incomplete.digest is None


def test_bounded_work_diagnostics() -> None:
    from tyvrana_protocol.attestation import AttestationWork

    data: dict[str, Any] = dict(
        exceeded="stream_bytes",
        stream_bytes=513,
        stream_items=12,
        bulk_elements=128,
        resources_completed=2,
        peak_buffer_bytes=128,
        current_category="images",
        current_resource="Texture",
        limits=dict(
            stream_bytes=512,
            stream_items=1000,
            bulk_elements=1024,
            buffer_bytes=256,
            resources=4096,
            elapsed_ms=30000,
            nesting=40,
        ),
        categories=[],
        heaviest=[],
    )
    assert AttestationWork.model_validate(data).exceeded == "stream_bytes"
    patches: list[dict[str, Any]] = [
        dict(stream_bytes=-1),
        dict(exceeded="unknown"),
        dict(current_resource="x" * 257),
    ]
    for patch in patches:
        with pytest.raises(ValidationError):
            AttestationWork.model_validate({**data, **patch})


def test_attestation_job_cannot_claim_unfinished_evidence() -> None:
    from tyvrana_protocol import DocumentAttestationJob, DocumentAttestationResponse

    queued = DocumentAttestationJob(job_id="work", state="queued")
    assert (
        DocumentAttestationResponse.model_validate(queued.model_dump()).root == queued
    )
    with pytest.raises(ValidationError, match="requires evidence"):
        DocumentAttestationJob(job_id="work", state="completed")
    with pytest.raises(ValidationError):
        DocumentAttestationJob(job_id="work", state="running", revision=-1)
    with pytest.raises(ValidationError):
        DocumentAttestationJob(job_id="work", state="running", poll_after_seconds=0)
