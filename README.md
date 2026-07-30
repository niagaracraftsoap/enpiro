# Enpiro

A lightweight Django and Channels service for recording and displaying
environmental readings from a BME690 connected to a Raspberry Pi Zero 2 W.

## Local setup

```bash
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py record_sample
python manage.py runserver 0.0.0.0:8000
```

Visit `http://localhost:8000/`. On the Pi, use its hostname or IP address.
The development server is provided by Daphne because `daphne` is the first
installed app.

Configuration is read from environment variables listed in `.env.example`.
Django does not load `.env` files itself; export those values from the shell or
set them in the eventual systemd unit.

## Current endpoints

- `/` — live dashboard
- `/api/readings/latest/` — latest reading as JSON
- `/ws/readings/` — live reading WebSocket
- `/admin/` — Django admin

## Semantic substrate

Enpiro carries the reusable `RootKey`, `SystemKey`, `Symbol`, `Term`, and
ordered `TermSymbol` substrate from `artofbodhi/core/models.py` as the local
`core` app. Art of Bodhi's card envelope and project settings are intentionally
not imported; environmental semantics live in `measurements/semantic.py`.

The substrate remains domain-neutral. Enpiro uses proxy models and interprets
two ordered Term shapes:

- Quick check: timestamp, temperature, pressure, humidity.
- Air-quality assessment: timestamp, percentage, validation flags.

Every item is a canonical compact binary Symbol. Units and meaning come only
from position in the environmental semantic layer; there are no field-name,
unit, source, or schema-marker Symbols. Substrate `created_at`/`modified_at`
remain internal—the first Symbol carries observation time.

The two streams are asynchronous. Gas resistance is transient calculation
input and is never persisted. Record standalone test Terms with:

```bash
python manage.py record_sample --temperature 21.5 --humidity 45 --pressure 1013.25
python manage.py record_assessment 88
```

## Demo data

Generate hourly, seeded Niagara Falls summer weather for June through August
2025:

```bash
python manage.py seed_summer
```

This creates 2,208 reproducible hourly observation Terms and 736 asynchronous
air-quality assessment Terms. Assessments arrive twenty minutes after every
third observation. Their gas inputs are transient. The dataset is synthetic,
not historical observation. `--replace` replaces environmental Terms whose
semantic timestamps fall within that summer.

## Raspberry Pi and BME690

The Pi-side Python I2C transport is included through `smbus2`. On Raspberry Pi
OS/Debian, enable I2C and install the system tools:

```bash
sudo raspi-config nonint do_i2c 0
sudo apt update
sudo apt install i2c-tools
```

After rebooting, verify that the device appears at `0x76` or `0x77`, then read
its identification registers:

```bash
i2cdetect -y 1
python manage.py probe_bme690
```

The BME690 variant ID should be `0x02`. This probe confirms communication but
does not perform compensated measurements. Production sampling should wrap
Bosch's official BME690 SensorAPI. Bosch BSEC 3.2 or newer is additionally
required to calculate IAQ; BSEC is a separately licensed binary download and
cannot be supplied as a normal pip dependency.

## Next steps

- [ ] Confirm the BME690 breakout-board manufacturer and I2C address.
- [ ] Integrate the official Bosch BME690 SensorAPI and, if its license is
      suitable, the matching aarch64 BSEC 3.x binary.
- [ ] Add a `record_sensor` command that writes quick checks and
      asynchronous air-quality assessments at independently configured intervals.
- [ ] Finalize the air-quality percentage calculation and validation flag rules;
      keep raw gas resistance transient.
- [ ] Add retention/downsampling rules so SQLite does not grow forever.
- [ ] Add chart/history endpoints and sensor-health information.
- [ ] Create systemd units for Daphne and the sensor recorder.
- [ ] Set a production secret, disable debug mode, and put a reverse proxy/TLS
      in front of the service if it will be reachable beyond the trusted LAN.
