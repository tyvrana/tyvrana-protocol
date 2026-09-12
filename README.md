# tyvrana-protocol

Application-independent data contracts between Tyvrana core and running
application adapters. This package provides typed messages, validation, and
UTF-8 JSON and binary chunk codecs. It is transport-independent: connection management and operation
execution belong to consumers of these contracts.

## Messages

Every top-level message has a required `type` discriminator:

| Python model | Wire `type` | Direction | Contents |
| --- | --- | --- | --- |
| `AdapterRegistration` | `adapter.register` | Adapter → core | Instance ID, application name, optional application version and project path, supported operations |
| `OperationRequest` | `operation.request` | Core → adapter | Request ID, operation name, arguments |
| `OperationSuccess` | `operation.success` | Adapter → core | Request ID, result, optional artifact descriptors |
| `OperationFailure` | `operation.failure` | Adapter → core | Request ID, structured error |
| `AdapterEvent` | `adapter.event` | Adapter → core | Event name, payload |
| `CancelRequest` | `operation.cancel` | Core → adapter | Request ID of the operation to cancel |

`Message` is the discriminated union of the operation and artifact control models. `ProtocolError` contains
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

## Artifacts

`ArtifactDescriptor` describes immutable bytes without embedding data or a storage
location. Its exact fields are:

| Field | Contract |
| --- | --- |
| `artifact_id` | Opaque 128-bit ID, exactly 32 lowercase hexadecimal digits |
| `name` | Optional nonblank display name, at most 255 characters; not a path |
| `media_type` | Lowercase MIME type/subtype without parameters, at most 127 characters |
| `byte_size` | Integer from 0 through 2^53−1 (portable JSON integer range) |
| `sha256` | SHA-256 of the exact bytes, 64 lowercase hexadecimal digits |

A successful operation may include `artifacts`, an ordered array of at most eight
unique descriptors. An empty array is omitted by the encoder. `result` remains a
required ordinary `JsonValue`; artifact bytes never belong in it. There are no
application-specific artifact models or metadata bags.

### Control and ordering

| Model | Wire `type` | Direction | Fields besides `type` |
| --- | --- | --- | --- |
| `ArtifactBegin` | `artifact.begin` | Adapter → core | `transfer_id`, `request_id`, `descriptor` |
| `ArtifactReady` | `artifact.ready` | Core → adapter | `transfer_id` |
| `ArtifactComplete` | `artifact.complete` | Adapter → core | `transfer_id` |
| `ArtifactAccepted` | `artifact.accepted` | Core → adapter | `transfer_id` |
| `ArtifactAbort` | `artifact.abort` | Either direction | `transfer_id`, `error` (`ProtocolError`) |

Every transfer belongs to an outstanding operation on that adapter connection.
Send `begin`, wait for `ready` (storage reserved), send chunks, send `complete`,
then wait for `accepted` (exact size and SHA-256 verified). Only then send
`operation.success` with the identical descriptor. Its artifact list must contain
exactly the artifacts completed for that request. Independent transfers may
interleave messages; each has independent offsets and hash state.

Generate separate random 128-bit IDs for artifacts and transfers, for example
`uuid4().hex`. IDs must not be reused; collisions must never overwrite existing
transfers or artifacts. Receivers reject unrecognized requests and conflicting
IDs. Limits are checked before `ready`; readiness reserves the full declared
size. Receiver policy sets artifact, storage, entry, and concurrency bounds well
below the wire integer maximum.

`abort` terminates the transfer and fails its operation; both endpoints clean all
artifacts associated with that unsuccessful request. `operation.cancel` cancels
all transfers for the request, including completed but not yet returned artifacts.
Disconnect and shutdown clean unfinished operations. A sender must stop producing
chunks when cancellation or rejection arrives. Already queued late chunks may be
rejected without affecting unrelated operations where correlation is available;
unattributable/malformed traffic may close the connection. Operation deadlines
bound transfer waits. Completion acknowledgements are not permanent storage
receipts; the receiving runtime owns artifact retention and release policy.

### Exact binary wire layout

On WebSocket, **all JSON controls are UTF-8 text messages**. **Binary messages
contain only artifact chunks**. The JSON codec still accepts/returns UTF-8 bytes;
use `encode_message(message).decode("utf-8")` when sending text. Do not infer a
message type by inspecting its first byte.

Each complete WebSocket binary message has this layout:

| Byte offsets | Length | Encoding |
| --- | --- | --- |
| 0–15 | 16 bytes | Transfer ID decoded from its 32 hex digits, in written byte order |
| 16–23 | 8 bytes | Unsigned 64-bit byte offset, big-endian (network order) |
| 24 onward | 1–65,536 bytes | Raw artifact payload |

There is no magic, version, padding, length prefix, JSON, or terminator. WebSocket
message boundaries provide the length. Transport-level fragmentation is allowed
only as fragments of one such bounded message; reassemble before decoding. Each
chunk's offset must equal the exact number of bytes already received, starting at
zero. Empty payloads, truncated headers, oversized chunks, gaps, repeats, and
bytes beyond the descriptor size are invalid. A zero-byte artifact uses
`begin` → `ready` → `complete` → `accepted` with no binary messages.

`encode_artifact_chunk(transfer_id, offset, payload)` and
`decode_artifact_chunk(data)` implement this framing; the latter returns an
immutable `ArtifactChunk`. Helpers enforce header/payload bounds, while receivers
validate active transfer ownership, ordering, total size, and incremental SHA-256.
Incomplete files must never be exposed as completed artifacts. No filesystem
paths, base64 in `JsonValue`, Python serialization, or shared-memory transport are
part of the contract.

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
