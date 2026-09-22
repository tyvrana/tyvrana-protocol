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
