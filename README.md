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
is broadcast to connected dashboards over a WebSocket.

## Storage

Observations are stored in SQLite using Enpiro's `Term`/`Symbol` substrate.
Each observation is represented by four ordered binary symbols:

1. A timezone-aware timestamp encoded as signed 64-bit microseconds since the
   Unix epoch.
2. Temperature encoded in tenths of a degree Celsius as a signed 16-bit
   integer.
3. Atmospheric pressure encoded in whole hectopascals as an unsigned 16-bit
   integer.
4. Relative humidity encoded in tenths of a percent as an unsigned 16-bit
   integer.

Equal encoded values share the same `Symbol` record. A `QuickCheck` proxy model
selects four-symbol terms and decodes them into environmental observations for
the rest of the application.

## Web interface

The application is built with [Django](https://www.djangoproject.com/).
[Channels](https://channels.readthedocs.io/) and
[Daphne](https://github.com/django/daphne) provide the ASGI and WebSocket
layer. [Redis](https://redis.io/) backs the channel layer and Django cache, and
[WhiteNoise](https://whitenoise.readthedocs.io/) serves static interface
assets.

The dashboard provides:

- Current temperature, relative humidity, and atmospheric pressure.
- Historical graphs with selectable 24-hour, 7-day, 30-day, complete, and
  custom ranges.
- Temperature and humidity condition indicators using thresholds configured
  in Django settings.
- Trend summaries calculated from the displayed readings.
- Live observations delivered over a WebSocket.
- Domain-scoped IndexedDB caching for immediate recovery after tab closures,
  device restarts, and temporary connectivity gaps.
- CSV downloads for one or more measurements and a selected time range.

The browser cache is a read-through copy, not the source of truth. Cached
observations render immediately, then the selected range is reconciled with
the server on page load, WebSocket reconnection, network recovery, and return
from a background tab. Graph points are positioned by their observation
timestamps so missed intervals remain visible instead of being compressed.

The JSON API exposes the latest observation and filtered measurement history.
A complete CSV export can be imported into an empty dataset with the
`import_readings_csv` management command.

The dashboard also includes a two-step reset flow. It offers a complete CSV
export before requiring an acknowledgement, the word `RESET`, and the reset
password. A successful reset deletes all observation terms and any symbols
that are no longer referenced.

## Deployment

The included deployment configuration runs:

- Daphne under a systemd user service.
- The sensor collection command from a persistent three-minute systemd timer.
- nginx as the local reverse proxy.
- Avahi service discovery for the local HTTP service.
- Apache as the TLS terminator and external reverse proxy, including the
  WebSocket route.

The Django secret key is loaded from a systemd credential. Production settings
disable Django debug mode, trust the HTTPS proxy header, use SQLite for stored
observations, and use separate Redis databases for Channels and caching.

## Tests

The automated test suite covers:

- Shared symbols and semantic observation encoding.
- Quantization and decoding of measurement values.
- Sensor adaptation, robust averaging, and outlier rejection.
- Dashboard, latest-reading, history, CSV, and reset endpoints.
- Condition-threshold system checks.
- WebSocket delivery.
- Complete CSV import and empty-dataset enforcement.

Hardware tests for the attached BME690 are opt-in so the regular suite can run
without access to the sensor.
