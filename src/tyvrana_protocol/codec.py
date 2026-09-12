"""Compact, deterministic UTF-8 JSON serialization without transport framing."""

import json

from pydantic import TypeAdapter

from .messages import Message

_MESSAGE_ADAPTER = TypeAdapter[Message](Message)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def decode_message(data: bytes) -> Message:
    """Decode one UTF-8 JSON message, raising ValueError for invalid input.

    Pydantic validation failures are reported as ValidationError, a ValueError
    subclass. Duplicate object keys are rejected at every nesting level.
    """
    value: object = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    return _MESSAGE_ADAPTER.validate_python(value)


def encode_message(message: Message) -> bytes:
    """Revalidate a message and encode sorted keys, compact JSON, and UTF-8.

    Revalidation catches invalid changes to nested JSON containers and objects
    made through Pydantic's validation-bypassing construction/copy methods.
    """
    validated = _MESSAGE_ADAPTER.validate_python(message)
    value: object = _MESSAGE_ADAPTER.dump_python(
        validated, mode="json", warnings="error"
    )
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
