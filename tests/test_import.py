import tyvrana_protocol


def test_package_imports() -> None:
    assert tyvrana_protocol.__name__ == "tyvrana_protocol"


def test_public_api_is_available_at_the_package_root() -> None:
    expected = {
        "AdapterEvent",
        "AdapterRegistration",
        "CancelRequest",
        "Identifier",
        "JsonValue",
        "Message",
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
