"""Environmental readings through Pimoroni's ``bme690`` package."""

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
import time


@dataclass(frozen=True)
class EnvironmentalReading:
    temperature_c: float
    pressure_hpa: float
    relative_humidity: float
    gas_resistance_ohms: float | None
    heat_stable: bool


@dataclass(frozen=True)
class AveragedEnvironmentalReading:
    observed_at: datetime
    temperature_c: float
    pressure_hpa: float
    relative_humidity: float
    retained_samples: int
    rejected_samples: int


def _median_absolute_deviation(values):
    centre = median(values)
    return centre, median(abs(value - centre) for value in values)


def average_without_outliers(
    readings: list[EnvironmentalReading],
    *,
    threshold: float = 3.5,
    observed_at: datetime | None = None,
) -> AveragedEnvironmentalReading:
    """Reject multivariate MAD outliers and average complete observations.

    A sample is rejected when any of its temperature, pressure, or humidity
    values has a modified z-score above ``threshold``. The conventional 0.6745
    scale makes MAD comparable with standard deviation for normal data.
    """
    if len(readings) < 5:
        raise ValueError("at least five readings are required")
    if threshold <= 0:
        raise ValueError("outlier threshold must be positive")

    fields = ("temperature_c", "pressure_hpa", "relative_humidity")
    statistics = {
        field: _median_absolute_deviation(
            [getattr(reading, field) for reading in readings]
        )
        for field in fields
    }

    def is_outlier(reading):
        for field in fields:
            centre, mad = statistics[field]
            deviation = abs(getattr(reading, field) - centre)
            if mad == 0:
                # Quantized sensor output can make the median absolute
                # deviation zero even during a small, healthy drift. Such a
                # field cannot provide a meaningful modified z-score, so let
                # the other fields decide whether the complete sample is an
                # outlier.
                continue
            elif 0.6745 * deviation / mad > threshold:
                return True
        return False

    retained = [reading for reading in readings if not is_outlier(reading)]
    if len(retained) < 3:
        raise RuntimeError(
            f"only {len(retained)} samples remained after outlier rejection"
        )

    return AveragedEnvironmentalReading(
        observed_at=observed_at or datetime.now(timezone.utc),
        temperature_c=sum(r.temperature_c for r in retained) / len(retained),
        pressure_hpa=sum(r.pressure_hpa for r in retained) / len(retained),
        relative_humidity=(
            sum(r.relative_humidity for r in retained) / len(retained)
        ),
        retained_samples=len(retained),
        rejected_samples=len(readings) - len(retained),
    )


class PimoroniBME690:
    """Small, testable adapter around Pimoroni's BME690 driver."""

    def __init__(self, *, address: int | None = None, sensor=None):
        if sensor is None:
            import bme690

            address = bme690.I2C_ADDR_PRIMARY if address is None else address
            sensor = bme690.BME690(address)
        self.sensor = sensor
        self._configure()

    def _configure(self):
        import bme690

        # bme690 1.0.0 returns the complete ctrl_meas register here. Masking
        # MODE_MSK prevents set_power_mode(blocking=True) from waiting forever.
        original_get_power_mode = self.sensor.get_power_mode

        def get_power_mode():
            mode = original_get_power_mode() & bme690.MODE_MSK
            # The upstream method also stores the unmasked register value.
            self.sensor.power_mode = mode
            return mode

        self.sensor.get_power_mode = get_power_mode
        self.sensor.set_humidity_oversample(bme690.OS_2X)
        self.sensor.set_pressure_oversample(bme690.OS_4X)
        self.sensor.set_temperature_oversample(bme690.OS_8X)
        self.sensor.set_filter(bme690.FILTER_SIZE_3)
        # Temperature, pressure and humidity do not require the gas hotplate.
        self.sensor.set_gas_status(bme690.DISABLE_GAS_MEAS)
        self.sensor.set_gas_heater_status(bme690.GAS_HEAT_DISABLE)

    def read(self) -> EnvironmentalReading:
        if not self.sensor.get_sensor_data():
            raise TimeoutError("BME690 did not produce a new reading")
        data = self.sensor.data
        return EnvironmentalReading(
            temperature_c=float(data.temperature),
            pressure_hpa=float(data.pressure),
            relative_humidity=float(data.humidity),
            gas_resistance_ohms=(
                float(data.gas_resistance) if data.heat_stable else None
            ),
            heat_stable=bool(data.heat_stable),
        )

    def collect_average(
        self,
        *,
        samples: int = 9,
        sample_interval: float = 1,
        outlier_threshold: float = 3.5,
    ) -> AveragedEnvironmentalReading:
        if samples < 5:
            raise ValueError("at least five samples are required")
        if sample_interval < 0:
            raise ValueError("sample interval cannot be negative")

        started_at = datetime.now(timezone.utc)
        readings = []
        for sample_number in range(samples):
            readings.append(self.read())
            if sample_interval and sample_number < samples - 1:
                time.sleep(sample_interval)
        finished_at = datetime.now(timezone.utc)
        midpoint = started_at + (finished_at - started_at) / 2
        return average_without_outliers(
            readings,
            threshold=outlier_threshold,
            observed_at=midpoint,
        )
