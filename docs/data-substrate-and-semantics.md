# Data substrate and semantic data management

## Purpose

Enpiro's data substrate is a generic persistence mechanism for reusable binary values and ordered compositions of those values.

The substrate does not know what the stored data means. It exists to provide:

- Deduplication of repeated values
- Ordered composition of values
- Stable references between stored values
- A flexible foundation for multiple semantic interpretations
- A single persisted representation of recorded information

Meaning belongs above the substrate.

## Base objects

The substrate consists of three models:

    Symbol
      └── one unique binary value

    Term
      └── an ordered collection of Symbols

    TermSymbol
      └── relationship between a Term, a Symbol, and its order

The relationships are:

    Term ──< TermSymbol >── Symbol

A Term does not contain a semantic type or named fields. It is simply an ordered set of references to Symbol objects.

The implementation is in:

- [core/models.py](../core/models.py)
- [core/migrations/0001_initial.py](../core/migrations/0001_initial.py)

## Deduplication

A binary value is resolved through Symbol.objects.resolve_clear(value).

    raw bytes
       ↓
    resolve_clear(bytes)
       ↓
    existing Symbol, or one newly created Symbol

Because Symbol.symbol is unique, repeated values are stored once and referenced many times.

For example, if many observations have the same encoded temperature, they can all reference one shared Symbol.

This is value-level deduplication. It is independent of the meaning later assigned to the value.

## Ordered terms

A term is assembled by creating TermSymbol relationships with explicit order:

    Term
    ├── order 0 → Symbol A
    ├── order 1 → Symbol B
    ├── order 2 → Symbol C
    └── order 3 → Symbol D

For an environmental observation, one semantic layer may interpret those positions as:

    order 0 → observed timestamp
    order 1 → temperature
    order 2 → pressure
    order 3 → relative humidity

The substrate itself does not know that interpretation.

## Semantic layer

The semantic layer should consist of ordinary Python functions, codecs, dataclasses, and query helpers—not additional persistence models for every interpretation.

A semantic layer may provide:

    encode value
      Python value → bytes

    decode value
      bytes → Python value

    encode term
      semantic record → ordered byte values

    decode term
      ordered byte values → semantic record

    find terms
      substrate query → matching Terms

For example:

    EnvironmentalReading
      observed_at
      temperature_c
      pressure_hpa
      relative_humidity

The semantic encoder converts the reading into ordered binary values, resolves those values into shared Symbol objects, and creates one Term.

The semantic decoder reads the ordered symbols from a term and reconstructs an EnvironmentalReading in memory.

## Persistence boundary

The intended write path is:

    sensor reading
       ↓
    semantic encoder
       ↓
    byte values
       ↓
    Symbol.objects.resolve_clear(...)
       ↓
    Term + ordered TermSymbol relationships
       ↓
    substrate only

The intended read path is:

    Term + ordered TermSymbol relationships
       ↓
    semantic decoder
       ↓
    in-memory domain value
       ↓
    API, dashboard, export, or telemetry

The substrate should make the data queryable through its own structure. A decoded projection is not required merely to make queries convenient.

A Symbol stores bytes, so the semantic layer must choose encodings deliberately:

- Exact lookup can use the unique index on Symbol.symbol.
- Ordered and range queries can use an order-preserving numeric encoding.
- TermSymbol.order identifies which semantic position a Symbol occupies.
- Substrate query helpers can join TermSymbol to Symbol and compare the encoded bytes directly.

A binary value is not automatically a sortable number. If a field must support ordering, its encoding must preserve numeric order under the database's byte ordering. Unsigned big-endian encodings work for non-negative integers; signed values need an order-preserving transformation before encoding.

This lets the substrate support equality, ordering, and range selection without storing decoded duplicates.

## Environmental observations

The initial environmental semantic profile represents:

    [source identifier, timestamp, temperature, pressure, relative humidity]

The BME690 gas-resistance measurement is intentionally outside the initial profile.

Additional semantic profiles can be introduced later without changing the substrate. For example, a future remote-telemetry profile could add device identity, sequence number, or reception metadata through a new ordered term shape.

The substrate remains unchanged; only the semantic encoder, decoder, and query helpers evolve.

## Querying

Substrate queries should be implemented as reusable query helpers or querysets that:

- Select candidate Term objects
- Retrieve ordered TermSymbol relationships
- Resolve their Symbol values
- Validate the expected semantic shape
- Decode matching terms into in-memory values

Query optimizations should improve retrieval of the substrate itself. They should not create a second persisted copy of decoded observations.

### Timestamp-first retrieval

Environmental terms already contain their own ordering key. The timestamp is
stored as the order-1 Symbol value in the environmental term:

    order 0 → source identifier
    order 1 → observed timestamp
    order 2 → temperature
    order 3 → pressure
    order 4 → relative humidity

The timestamp uses a fixed-width order-preserving encoding for the dates used
by Enpiro. Therefore, the `TermSymbol` rows at `order=1` can be used as the
substrate's candidate and sorting table. Retrieval should begin there, apply
timestamp bounds or descending order, and only then load and decode the
corresponding Terms.

In particular, a latest-reading request should be a descending timestamp
lookup with a small validation window, followed by one ordered-symbol
prefetch. It should not reconstruct the complete environmental history.

The encoded observation timestamp is deliberately different from persistence
metadata such as a hypothetical `Term.created_at` or `Symbol.created_at`:

- the observation timestamp represents when the environmental condition was
  measured;
- a Term persistence timestamp would represent when data was inserted;
- a Symbol persistence timestamp would represent when a deduplicated value was
  first seen, not when a particular observation used it.

Imports, delayed uploads, and out-of-order readings make persistence time an
unsafe substitute for measurement time. The semantic timestamp remains the
authoritative key for history, range filtering, exports, and latest-reading
selection.

No decoded projection or additional QuickSync model is needed for this
optimization.

## Current transition

The former QuickCheck and QuickCheckIndex implementation represented an
earlier projection-based approach. The substrate-only migration converts
existing four-symbol environmental Terms into source-aware five-symbol Terms,
using `local` for readings made by the Pi Zero. It removes the decoded index
table and proxy model, and keeps decoding in semantic functions and in-memory
values.

Air-quality assessments are a separate semantic shape:

    [timestamp, percentage]

The percentage is an integer from 0 through 100. It is not a nullable member of
the environmental shape because an assessment is a separate event that may not
occur for every environmental reading.

## Design principle

> The substrate stores structure. The semantic layer supplies meaning.

This separation allows the same persistence mechanism to support environmental readings, remote telemetry, device metadata, and future data types without embedding application-specific assumptions in the base models.
