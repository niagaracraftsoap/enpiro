# Native Enpiro service plan

## Intent

Enpiro will receive a project-specific C implementation of its persistence
and delivery path. It will be inspired by the useful mechanics in Soapcore,
but it will not link to, copy from, or depend on the Soapcore project.

The result will remain specific to the Raspberry Pi warehouse monitor and its
environmental semantic profile.

## Preserved contracts

The migration preserves:

- the browser routes and JSON response shapes;
- CSV export behavior;
- the five-symbol environmental term layout;
- the order-preserving encoded observation timestamp;
- source-aware environmental observations;
- existing recorded history through an explicit migration or compatible
  database opening path;
- systemd scheduling and service supervision;
- nginx static-file delivery during the transition.

The semantic layer remains above the storage layer. The C store will not add
environment-specific columns or a QuickSync projection.

This is intentionally a clear-only implementation. Enpiro does not need
Soapcore's cryptographic context, anchor, RootKey, SystemKey, encrypted
Symbols, mutation sidecars, file-backed values, or generic multi-application
capability surface.

## Native components

The new implementation will be divided into small project-local components:

```text
native/enpiro_store
    SQLite schema and connection lifecycle
    Symbol deduplication
    ordered Term and TermSymbol creation
    timestamp-first queries
    bounded payload cache

native/enpiro_environment
    environmental byte codecs
    five-symbol term validation
    observation JSON/CSV projection

native/enpiro_http
    minimal HTTP request parsing
    route dispatch
    JSON and CSV responses
    reset request validation
```

The native HTTP process will replace Gunicorn for the Enpiro web service. It
will be a small synchronous service appropriate for the Pi’s low-concurrency
local monitor, supervised directly by systemd.

## Retrieval design

The store will use the existing environmental timestamp Symbol as the
measurement ordering key. Read paths will:

1. select timestamp-bearing TermSymbol relationships;
2. apply timestamp bounds or descending order;
3. impose an explicit result limit or continuation cursor;
4. load only the corresponding ordered symbols;
5. decode at the semantic boundary.

The store will use indexes appropriate to these paths, including the existing
Term/TermSymbol order constraint and a reverse relationship index beginning
with `order` and `symbol_id`.

Clear Symbol payloads will have a bounded process-local cache keyed by Symbol
ID. SQLite remains authoritative; eviction and process restart are harmless.

The native persistence graph is deliberately limited to:

```text
Symbol
  id
  clear byte blob

Term
  id

TermSymbol
  term_id
  symbol_id
  order
```

The `TermSymbol` relationship is the occurrence record. Its `order` gives the
semantic layer the positions needed to interpret an environmental term. No
anchor, encryption metadata, mutation reference, or application-specific
field belongs in this project-specific substrate.

## Migration sequence

### Phase 1: native store and read verification

Implement the C store against the Enpiro substrate contract and test it
against representative existing SQLite data. Keep Django as the reference
writer and web service while native reads are verified.

The initial store and environmental semantic slice is implemented in
`native/`. It builds with CMake against SQLite and currently verifies clear
Symbol reuse, ordered Term identity, timestamp-first candidate retrieval, and
the five-position environmental codec. The native HTTP process remains a
later phase.

### Phase 2: native HTTP shadow service

Run the C HTTP service on a separate local port. Compare its latest, history,
CSV, and error responses with the existing Django endpoints.

### Phase 3: native sensor writer

Move environmental encoding and Term creation into the native store writer.
The BME690 sampling and robust averaging can initially remain in the existing
collector while a narrow native recording command accepts the averaged values.
This phase is now implemented by `native/record_sensor.py` and
`native/enpiro_record`: Python retains the tested BME690 sampling and robust
outlier rejection, while C performs the clear Symbol/Term/TermSymbol write.
The `enpiro-sensor.service` unit uses this path after the native binary has
been installed to `native-install/bin/enpiro_record`.

The deployment build installs that binary with CMake, for example:
`cmake --install native/.sqlite-dev/build --prefix native-install`. The
installation directory is a runtime artifact and is intentionally ignored by
version control.

There is no copy or second database. The recorder opens the same SQLite path
used by Django, so existing Terms remain readable and new Terms become
visible to the existing browser routes immediately.

### Phase 4: web cutover

Switch systemd from Gunicorn/Django to the native service. Keep nginx in front
for static assets and reverse proxying. Preserve the existing browser client
and observe the service under normal polling and export use.

### Phase 5: retirement

After dual-path verification and a rollback window, remove Django, Gunicorn,
the ORM migrations, and the old web service path from the deployment.

## Safety requirements

- Never overwrite or reinterpret the production database without a verified
  backup and a tested migration path.
- Keep the old Django service available until native latest/history/CSV/reset
  behavior has been compared.
- Treat persisted Symbols, Terms, and TermSymbols as immutable after creation.
- Bound every native query and response allocation.
- Keep reset disabled or explicitly protected until its native implementation
  is tested against the existing confirmation flow.
- Add query-plan and response-contract tests before cutover.

## Completion criteria

The migration is complete when:

- the native service serves all current browser routes;
- the sensor timer writes through the native store;
- existing history is readable without Django;
- native response values match the semantic reference tests;
- the browser cache and polling behavior remain functional;
- Gunicorn and Django are no longer required in deployment;
- the native service passes memory-safety and malformed-request tests.
