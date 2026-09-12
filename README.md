# tyvrana-protocol

Application-independent data contracts between Tyvrana core and running
application adapters. This package provides typed messages, validation, and a
UTF-8 JSON codec. It is transport-independent: connection management and operation
execution belong to consumers of these contracts.

## Messages

Every top-level message has a required `type` discriminator:

| Python model | Wire `type` | Direction | Contents |
| --- | --- | --- | --- |
| `AdapterRegistration` | `adapter.register` | Adapter → core | Instance ID, application name, optional application version and project path, supported operations |
| `OperationRequest` | `operation.request` | Core → adapter | Request ID, operation name, arguments |
| `OperationSuccess` | `operation.success` | Adapter → core | Request ID, result |
| `OperationFailure` | `operation.failure` | Adapter → core | Request ID, structured error |
| `AdapterEvent` | `adapter.event` | Adapter → core | Event name, payload |
| `CancelRequest` | `operation.cancel` | Core → adapter | Request ID of the operation to cancel |

`Message` is the discriminated union of these six models. `ProtocolError` contains
a string `code`, a nonblank human-readable `message`, and optional JSON `details`.
Error codes are extensible strings, not a fixed catalog.

IDs are opaque, case-sensitive strings matching `[A-Za-z0-9][A-Za-z0-9._:-]*`.
Adapters assign unique IDs to running instances; core assigns unique IDs to
requests. UUID strings are suitable. Responses and cancellations carry the
original request ID. Uniqueness across messages is the sender's responsibility.

Operation and event names use two or more lowercase dotted segments, each
matching `[a-z][a-z0-9_]*`. Names such as `document.inspect` are illustrations;
this package does not define application operations or event payload schemas.
Registrations reject duplicate operation names and may advertise an empty list.
Project paths are opaque strings interpreted by the application that owns them.

`JsonValue` represents null, booleans, integers, finite floats, strings, arrays,
and objects with string keys. Arguments, results, and event payloads are required
and may contain any JSON value, including `{}`, `[]`, and `null`. Absent
registration metadata and error details are omitted when encoding; explicitly
passing `None` to those optional fields also omits them. Required payload fields
and nested object entries retain meaningful `null` values.

Models reject extra fields and malformed values without coercing strings to
numbers or arbitrary Python objects to JSON. Model fields are frozen and
advertised operations are stored as a tuple (a JSON array on the wire). Nested
JSON lists and dictionaries remain ordinary mutable containers; validation
copies input containers and encoding revalidates their contents.

## Python usage

```python
from tyvrana_protocol import (
    AdapterRegistration,
    OperationRequest,
    decode_message,
    encode_message,
)

registration = AdapterRegistration(
    type="adapter.register",
    instance_id="adapter-a",
    application="Example Editor",
    application_version="2026.9",
    operations=("document.inspect",),
)
registration_bytes = encode_message(registration)

request = OperationRequest(
    type="operation.request",
    request_id="request-1",
    operation="document.inspect",
    arguments={},
)
wire = encode_message(request)
received = decode_message(wire)
assert isinstance(received, OperationRequest)
assert received == request
```

Both codec functions use UTF-8 **bytes** as the transport boundary. Encoding
produces one compact JSON object with recursively sorted keys and no trailing
newline or framing. Decoding constructs the matching model and rejects unknown
message types, unexpected fields, invalid JSON, duplicate object keys, and
non-finite numbers. Invalid input raises `ValueError`, including Pydantic's
`ValidationError` for model validation failures.

The Python models are canonical. Generate JSON Schema for consumers in other
languages using Pydantic; no generated schema needs to be stored in this package:

```python
from pydantic import TypeAdapter

from tyvrana_protocol import Message

schema = TypeAdapter(Message).json_schema()
```

## Development

Requires Python 3.12+ and uv. From this repository, create its local environment
and install the package and development dependencies:

```sh
uv sync --locked --python 3.12
```

Run the checks:

```sh
uv run --locked pytest
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
```

To format Python files, run `uv run --locked ruff format .`.

Build a wheel and source distribution with `uv build`.
