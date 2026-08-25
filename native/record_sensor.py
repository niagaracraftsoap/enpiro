"""Sample the BME690 in Python and persist the averaged reading natively."""

from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from measurements.bme690_sensor import PimoroniBME690  # noqa: E402

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def timestamp_us(value: datetime) -> int:
    return round((value.astimezone(timezone.utc) - EPOCH).total_seconds() * 1_000_000)


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--recorder", required=True, type=Path)
    parser.add_argument("--address", default="0x76")
    parser.add_argument("--samples", type=int, default=9)
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--outlier-threshold", type=float, default=3.5)
    parser.add_argument("--source", default="local")
    options = parser.parse_args()
    sensor = PimoroniBME690(address=int(options.address, 0))
    average = sensor.collect_average(
        samples=options.samples,
        sample_interval=options.sample_interval,
        outlier_threshold=options.outlier_threshold,
    )
    result = subprocess.run(
        [str(options.recorder), str(options.database), str(timestamp_us(average.observed_at)),
         f"{average.temperature_c:.6f}", f"{average.pressure_hpa:.6f}",
         f"{average.relative_humidity:.6f}", options.source],
        check=True, text=True, capture_output=True,
    )
    print(
        f"Recorded observation Term #{result.stdout.strip()}: "
        f"{average.temperature_c:.2f} C, {average.pressure_hpa:.2f} hPa, "
        f"{average.relative_humidity:.2f} %RH ({average.retained_samples} retained, "
        f"{average.rejected_samples} rejected)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
