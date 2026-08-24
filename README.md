# Enpiro

Enpiro is a warehouse environmental monitor for the space where we store soap
and skincare products. It records temperature, relative humidity, and
atmospheric pressure, presents current and historical readings in a web
dashboard, and exports recorded data as CSV.

Temperature and humidity can affect the quality and longevity of the things we
make. Atmospheric pressure is recorded alongside them as additional
environmental context.

## Hardware

Enpiro runs on a [Raspberry Pi Zero 2 W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/).
Its environmental readings come from a
[Bosch BME690](https://www.bosch-sensortec.com/products/environmental-sensors/gas-sensors/bme690/)
mounted on a
[Pimoroni BME690 breakout](https://shop.pimoroni.com/products/bme690-breakout).
The sensor measures temperature, relative humidity, and atmospheric pressure
inside the warehouse.

At the hardware boundary, the
[`bme690`](https://pypi.org/project/bme690/) library provides the sensor
driver and [`smbus2`](https://pypi.org/project/smbus2/) provides access to the
Pi's I²C bus.

## Collection

The `record_sensor` management command collects nine sensor samples at
one-second intervals. It applies multivariate median absolute deviation
outlier rejection across temperature, pressure, and humidity, then averages
the retained samples into one observation.

A systemd timer runs the command every three minutes. Each saved observation
is made available to dashboards through the JSON API.

## Storage

Observations are stored in SQLite using Enpiro's `Term`/`Symbol` substrate.
Each observation is represented by five ordered binary symbols:

1. A source identifier such as `local` or `pico-01`.
2. A timezone-aware timestamp encoded as signed 64-bit microseconds since the
   Unix epoch.
3. Temperature encoded in tenths of a degree Celsius as a signed 16-bit
   integer.
4. Atmospheric pressure encoded in whole hectopascals as an unsigned 16-bit
   integer.
5. Relative humidity encoded in tenths of a percent as an unsigned 16-bit
   integer.

Equal encoded values share the same `Symbol` record. Semantic query helpers
validate the ordered shape and decode Terms into environmental observations for
the rest of the application. No decoded observation index is persisted.

The encoded observation timestamp is also the substrate retrieval key. History
queries begin with timestamp-bearing `TermSymbol` rows at order 1, and the
latest-reading query orders those rows descending before loading the matching
Term symbols. This avoids scanning and decoding the complete history for a
single latest reading. A persistence-time `created_at` field is not required:
the measurement timestamp remains authoritative for imported, delayed, or
out-of-order readings.

Air-quality assessments are independent Terms containing a timestamp and an
integer percentage from 0 through 100. They are not nullable fields on
environmental observations and are not collected until that semantic profile
is implemented.

## Web interface

The application is built with [Django](https://www.djangoproject.com/).
[Gunicorn](https://gunicorn.org/) runs the WSGI application. Local
[nginx](https://nginx.org/) serves static interface assets and proxies dynamic
requests to Gunicorn.

The dashboard provides:

- Current temperature, relative humidity, and atmospheric pressure.
- Historical graphs with selectable 24-hour, 7-day, 30-day, complete, and
  custom ranges.
- Temperature and humidity condition indicators using thresholds configured
  in Django settings.
- Trend summaries calculated from the displayed readings.
- Live observations refreshed by lightweight polling of the latest-reading API.
- Domain-scoped IndexedDB caching for immediate recovery after tab closures,
  device restarts, and temporary connectivity gaps.
- CSV downloads for one or more measurements and a selected time range.

The initial dashboard GET retrieves only the latest observation needed for the
current-condition cards. The browser then requests the selected graph range
from the history API, which uses the encoded observation timestamp to select
substrate candidates. Live latest-reading polling begins on its regular
30-second interval rather than duplicating the initial page request.

The browser cache is a read-through copy, not the source of truth. Cached
observations render immediately, then the selected range is reconciled with
the server on page load, periodic polling, network recovery, and return
from a background tab. Graph points are positioned by their observation
timestamps so missed intervals remain visible instead of being compressed.
Observed lines stop when consecutive samples are missing. Rough dashed waves
mark those intervals and the chart labels them explicitly as non-data rather
than presenting an interpolated slope as a measurement.
Observation timestamps are recorded, transferred, and cached as UTC. The
dashboard formats them in the browser's local timezone, and converts locally
entered date ranges back to UTC before requesting data from the server.

The JSON API exposes the latest observation and filtered measurement history.
A complete CSV export can be imported into an empty dataset with the
`import_readings_csv` management command.

The dashboard also includes a two-step reset flow. It offers a complete CSV
export before requiring an acknowledgement, the word `RESET`, and the reset
password. A successful reset deletes all observation terms and any symbols
that are no longer referenced.

## Deployment

The included deployment configuration runs:

- Gunicorn under a systemd user service.
- The sensor collection command from a persistent three-minute systemd timer.
- nginx as the local reverse proxy and static file server.
- Avahi service discovery for the local HTTP service.
- Apache as the TLS terminator and external reverse proxy.

Run `manage.py collectstatic --noinput` as part of deployment updates (after
pulling changes), rather than on every web-service restart.

The Django secret key is loaded from a systemd credential. Production settings
disable Django debug mode, trust the HTTPS proxy header, and use SQLite for
stored observations.

## Tests

The automated test suite covers:

- Shared symbols and semantic observation encoding.
- Quantization and decoding of measurement values.
- Sensor adaptation, robust averaging, and outlier rejection.
- Dashboard, latest-reading, history, CSV, and reset endpoints.
- Condition-threshold system checks.
- Complete CSV import and empty-dataset enforcement.

Hardware tests for the attached BME690 are opt-in so the regular suite can run
without access to the sensor.
