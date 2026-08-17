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

The decoded domain value should not be persisted again merely to make it easier to query.

## Environmental observations

The initial environmental semantic profile represents:

    [timestamp, temperature, pressure, relative humidity]

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

## Current transition

The existing QuickCheck and QuickCheckIndex implementation represents an earlier projection-based approach. QuickCheckIndex stores decoded environmental fields separately from the substrate.

The intended direction is to make the substrate the sole persisted data representation and replace semantic models or decoded indexes with semantic functions and in-memory values. Existing data must be migrated carefully before removing any transitional projection.

## Design principle

> The substrate stores structure. The semantic layer supplies meaning.

This separation allows the same persistence mechanism to support environmental readings, remote telemetry, device metadata, and future data types without embedding application-specific assumptions in the base models.