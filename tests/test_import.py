import tyvrana_protocol


def test_package_imports() -> None:
    assert tyvrana_protocol.__name__ == "tyvrana_protocol"


def test_public_api_is_available_at_the_package_root() -> None:
    expected = {
        "AdapterRuntime",
        "ProofLease",
        "ProofArtifact",
        "ProofHostStart",
        "ProofHostStatus",
        "ProofHostControl",
        "DocumentRestoreJob",
        "DocumentRestoreRequest",
        "DocumentRestoreResult",
        "DocumentRestoreTarget",
        "DocumentState",
        "DocumentMutationJob",
        "DocumentMutationRequest",
        "DocumentMutationResult",
        "DocumentAttestation",
        "DocumentAttestationJob",
        "DocumentAttestationResponse",
        "ResourceReference",
        "ResourceInspectionRequest",
        "ResourceInspectionResult",
        "ResourceObservation",
        "ARTIFACT_HEADER_SIZE",
        "MAX_ARTIFACT_CHUNK_SIZE",
        "ArtifactChunk",
        "ArtifactAbort",
        "ArtifactAccepted",
        "ArtifactBegin",
        "ArtifactComplete",
        "ArtifactDescriptor",
        "ArtifactReady",
        "ArtifactId",
        "TransferId",
        "decode_artifact_chunk",
        "encode_artifact_chunk",
        "AdapterEvent",
        "AdapterRegistration",
        "CancelRequest",
        "Identifier",
        "JsonValue",
        "Message",
        "OperationContract",
        "OperationFailure",
        "OperationRequest",
        "OperationSuccess",
        "ProtocolError",
        "QualifiedName",
        "decode_message",
        "encode_message",
    }
    assert set(tyvrana_protocol.__all__) == expected
    for name in expected:
        assert getattr(tyvrana_protocol, name) is not None
