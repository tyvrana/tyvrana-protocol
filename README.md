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
| `OperationRequest` | `operation.request` | Core → adapter | Request ID, operation name, arguments, optional input artifact descriptors |
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
Registrations contain up to 512 `OperationContract` values with unique names and
may advertise an empty list. Each contract contains a description, self-contained
argument/result JSON Schemas, effect (`read_only`, `mutating`, `transient`, or
`lifecycle`), execution (`synchronous`, `job_start`, `job_status`, or `lifecycle`),
interactive-context requirements and input/output artifact behavior. Schemas are
limited to 128 KiB each and references must be local. Generate them from the
adapter's actual validators; cross-field/native-state rules still require runtime
validation and a useful error. Defaults describe omitted arguments and must not be
blindly materialized by clients, since explicit fields can affect host semantics.

Core can expose selected contracts without repeated application round trips.
`operation_names` is a local derived convenience; only contracts travel in
registration. Contracts describe behavior, not permission grants, transaction
promises, arbitrary-code execution or versioned compatibility interfaces.
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
    OperationContract,
    decode_message,
    encode_message,
)

registration = AdapterRegistration(
    type="adapter.register",
    instance_id="adapter-a",
    application="Example Editor",
    application_version="2026.9",
    operations=(
        OperationContract(
            name="document.inspect",
            description="Inspect the current document without modifying it.",
            arguments_schema={"type": "object", "additionalProperties": False},
            result_schema={"type": "object"},
            effect="read_only",
            execution="synchronous",
        ),
    ),
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

An operation request or successful result may include `artifacts`, an ordered
array of at most eight descriptors with unique artifact IDs. An empty array is
omitted by the encoder; explicit null is invalid. `arguments` and `result` remain
required ordinary `JsonValue`; artifact bytes never belong in them. There are no
application-specific artifact models or metadata bags. Requests reference input
bytes already accepted by the adapter; results reference output bytes already
accepted by core. Each list must match the complete descriptors transferred for
that request and direction, including size and SHA-256.

### Control and ordering

| Model | Wire `type` | Direction | Fields besides `type` |
| --- | --- | --- | --- |
| `ArtifactBegin` | `artifact.begin` | Sender → receiver | `transfer_id`, `request_id`, `descriptor` |
| `ArtifactReady` | `artifact.ready` | Receiver → sender | `transfer_id` |
| `ArtifactComplete` | `artifact.complete` | Sender → receiver | `transfer_id` |
| `ArtifactAccepted` | `artifact.accepted` | Receiver → sender | `transfer_id` |
| `ArtifactAbort` | `artifact.abort` | Either direction | `transfer_id`, `error` (`ProtocolError`) |

Every transfer belongs to one request on that adapter connection. The same
controls and binary framing work in both directions:

- **Inputs, core → adapter:** send `begin`, wait for `ready` (storage reserved),
  send chunks, send `complete`, then wait for `accepted` (exact size and SHA-256
  verified). After all inputs are accepted, send `operation.request` with their
  identical descriptors. The adapter must not execute an incomplete request.
- **Outputs, adapter → core:** the operation must already be outstanding. Follow
  the same handshake, then send `operation.success` with its output descriptors.

Input `begin` establishes request-scoped staging before an operation exists in
the adapter execution queue. Receivers bound staged requests, storage, entries,
and transfer waits, and reject conflicting or unclaimed data. Request IDs cannot
be reused on a connection. Independent transfers may interleave messages; each
has independent offsets and hash state. Input and output attachments are separate
sets, not implicitly echoed between request and response.

Generate separate random 128-bit IDs for artifacts and transfers, for example
`uuid4().hex`. Transfer IDs must not be reused; collisions must never overwrite
active data. An artifact ID identifies immutable content and may be reused by
later or concurrent requests, each with a fresh transfer ID and independent
request-scoped receiver storage. Receivers reject unrecognized output requests,
conflicting descriptors, and duplicate attachments. Limits are checked before
`ready`; readiness reserves the full declared
size. Receiver policy sets artifact, storage, entry, and concurrency bounds well
below the wire integer maximum.

`abort` terminates the transfer and fails its operation; both endpoints clean all
request-scoped artifacts associated with that unsuccessful request.
`operation.cancel` also applies before `operation.request`: it cancels all input
and output transfers for the request, including accepted staging data. Cancelling
one use does not release the sender's reusable source artifact or another request's
copy. An adapter releases staged input files after completion/failure; core owns
the lifetime of imported source artifacts independently.
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
