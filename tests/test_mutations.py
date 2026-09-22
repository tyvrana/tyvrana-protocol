"""Mutation receipts cannot qualify unfinished work or cross document lineages."""

from typing import Any

import pytest
from pydantic import ValidationError

from tyvrana_protocol import DocumentMutationJob, DocumentMutationResult


def receipt() -> dict[str, Any]:
    evidence = dict(
        host_session_id="host",
        document_session_id="doc",
        project_id="saved",
        format="native",
        digest="a" * 64,
        status="complete",
        resource_count=1,
        omissions=[],
        elapsed_ms=1.0,
        resource_scope="outgoing-closure",
    )
    return dict(
        mutation_id="work",
        result={},
        before=evidence,
        after={**evidence, "digest": "b" * 64},
    )


def test_qualified_receipt_and_terminal_state() -> None:
    value = DocumentMutationResult.model_validate(receipt())
    result = DocumentMutationJob(job_id="work", state="completed", result=value)
    assert DocumentMutationJob.model_validate_json(result.model_dump_json()) == result
    patches: list[dict[str, Any]] = [
        dict(state="queued", result=value),
        dict(state="completed"),
        dict(state="completed", result=value, job_id="other"),
    ]
    for patch in patches:
        with pytest.raises(ValidationError):
            DocumentMutationJob.model_validate({"job_id": "work", **patch})


@pytest.mark.parametrize(
    "field",
    [
        "host_session_id",
        "document_session_id",
        "project_id",
        "format",
        "resource_scope",
    ],
)
def test_receipt_rejects_mixed_identity(field: str) -> None:
    data = receipt()
    data["after"][field] = "different"
    with pytest.raises(ValidationError):
        DocumentMutationResult.model_validate(data)


def test_receipt_rejects_incomplete_or_unscoped_evidence() -> None:
    data = receipt()
    data["after"].update(status="unsupported", digest=None, omissions=["unknown cache"])
    with pytest.raises(ValidationError):
        DocumentMutationResult.model_validate(data)
    data = receipt()
    data["before"]["resource_scope"] = None
    with pytest.raises(ValidationError):
        DocumentMutationResult.model_validate(data)
