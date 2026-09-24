"""A destructive restore is explicit and carries both current and target identity."""

import pytest
from pydantic import ValidationError

from tyvrana_protocol import (
    DocumentAttestation,
    DocumentRestoreRequest,
    DocumentRestoreResult,
)


def request() -> dict[str, object]:
    return dict(
        mutation_id="restore",
        operation="editor.file.open",
        locator="/trusted.document",
        discard_current=True,
        current=dict(
            host_session_id="host",
            document_session_id="loaded",
            project_id=None,
            format="canonical",
            digest="a" * 64,
        ),
        target=dict(
            project_id="project",
            format="canonical",
            digest="b" * 64,
            file_sha256="c" * 64,
        ),
    )


@pytest.mark.parametrize("authorization", [False, None, 1, "true"])
def test_explicit_discard(authorization: object) -> None:
    value = request()
    value["discard_current"] = authorization
    with pytest.raises(ValidationError):
        DocumentRestoreRequest.model_validate(value)


def test_restore_can_change_document_session_but_not_host() -> None:
    value = DocumentRestoreRequest.model_validate(request())
    assert value.current.project_id is None
    before = DocumentAttestation(
        host_session_id="host",
        document_session_id="doc",
        project_id="saved",
        format="native",
        digest="a" * 64,
        status="complete",
        resource_count=1,
        omissions=[],
        elapsed_ms=1.0,
        resource_scope="closure",
    )
    after = before.model_copy(update={"document_session_id": "reopened"})
    receipt = DocumentRestoreResult(
        mutation_id="restore", result={}, before=before, after=after
    )
    assert receipt.after.document_session_id != receipt.before.document_session_id
    with pytest.raises(ValidationError):
        DocumentRestoreResult(
            mutation_id="restore",
            result={},
            before=before,
            after=after.model_copy(update={"host_session_id": "other"}),
        )
