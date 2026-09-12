"""Portable JSON values and names shared by the wire contracts."""

from typing import Annotated

from pydantic import BeforeValidator, Field, StrictBool, StrictInt, StrictStr


def _require_json_type(value: object) -> object:
    if type(value) not in (type(None), bool, int, float, str, list, dict):
        raise ValueError(
            "Expected a JSON null, boolean, number, string, array, or object"
        )
    # Escaped lone surrogates can survive JSON parsing but cannot round-trip UTF-8.
    if isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, dict):
        for key in value:
            if isinstance(key, str):
                key.encode("utf-8")
    return value


type JsonValue = Annotated[
    None
    | StrictBool
    | StrictInt
    | Annotated[float, Field(strict=True, allow_inf_nan=False)]
    | StrictStr
    | list[JsonValue]
    | dict[StrictStr, JsonValue],
    BeforeValidator(_require_json_type),
]
"""Recursive JSON data; numbers must be finite and object keys must be strings."""

type Identifier = Annotated[
    str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
]
"""An opaque, case-sensitive ASCII token; UUID strings are suitable identifiers."""

type QualifiedName = Annotated[
    str, Field(strict=True, pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
]
"""Two or more lowercase dotted segments, each beginning with a letter."""

type ArtifactId = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$")]
"""Opaque 128-bit identifier written as exactly 32 lowercase hexadecimal digits."""

type TransferId = ArtifactId
"""An independently generated 128-bit transfer identifier; never reused."""
