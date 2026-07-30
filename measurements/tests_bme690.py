from types import SimpleNamespace
from unittest import TestCase, mock

from .bme690_sensor import (
    EnvironmentalReading,
    PimoroniBME690,
    average_without_outliers,
)


def reading(temperature, pressure=1012.0, humidity=45.0):
    return EnvironmentalReading(temperature, pressure, humidity, None, False)


class RobustAverageTests(TestCase):
    def test_rejects_a_clear_outlier_then_averages_retained_samples(self):
        """Prevent a corrupt multivariate sample from distorting an observation."""
        result = average_without_outliers(
            [
                reading(20.0),
                reading(20.1),
                reading(20.2),
                reading(20.3),
                reading(20.4),
                reading(80.0, pressure=4000, humidity=100),
            ]
        )
        self.assertAlmostEqual(result.temperature_c, 20.2)
        self.assertEqual(result.pressure_hpa, 1012.0)
        self.assertEqual(result.relative_humidity, 45.0)
        self.assertEqual(result.retained_samples, 5)
        self.assertEqual(result.rejected_samples, 1)

    def test_requires_enough_samples_for_robust_rejection(self):
        """Reject sample sets too small for the configured robust estimator."""
        with self.assertRaisesRegex(ValueError, "at least five"):
            average_without_outliers([reading(20)] * 4)

    def test_accepts_healthy_quantized_drift_when_mad_is_zero(self):
        """Keep normal sensor quantization from rejecting every collected sample."""
        result = average_without_outliers(
            [
                reading(22.17, 977.42, 52.512),
                reading(22.16, 977.42, 52.536),
                reading(22.16, 977.41, 52.548),
                reading(22.16, 977.41, 52.536),
                reading(22.16, 977.41, 52.523),
                reading(22.16, 977.40, 52.561),
                reading(22.15, 977.40, 52.572),
                reading(22.15, 977.40, 52.609),
                reading(22.14, 977.40, 52.545),
            ]
        )
        self.assertGreaterEqual(result.retained_samples, 3)
        self.assertLess(result.rejected_samples, 9)


class FakeSensor:
    def __init__(self):
        self.data = SimpleNamespace(
            temperature=22.5,
            pressure=1012.8,
            humidity=45.0,
            gas_resistance=90_000,
            heat_stable=True,
        )

    def get_power_mode(self):
        self.power_mode = 0b10101101
        return 0b10101101

    def get_sensor_data(self):
        return True

    def __getattr__(self, name):
        if name.startswith(("set_", "select_")):
            return mock.Mock()
        raise AttributeError(name)


class PimoroniAdapterTests(TestCase):
    @mock.patch.dict(
        "sys.modules",
        {
            "bme690": SimpleNamespace(
                MODE_MSK=0x03,
                OS_2X=2,
                OS_4X=3,
                OS_8X=4,
                FILTER_SIZE_3=2,
                DISABLE_GAS_MEAS=0,
                GAS_HEAT_DISABLE=1,
            )
        },
    )
    def test_reads_compensated_environmental_values(self):
        """Guard the driver adapter and its workaround for unmasked power modes."""
        adapter = PimoroniBME690(sensor=FakeSensor())
        reading = adapter.read()
        self.assertEqual(reading.temperature_c, 22.5)
        self.assertEqual(reading.pressure_hpa, 1012.8)
        self.assertEqual(reading.relative_humidity, 45.0)
        self.assertEqual(reading.gas_resistance_ohms, 90_000)
        self.assertEqual(adapter.sensor.get_power_mode(), 1)
        self.assertEqual(adapter.sensor.power_mode, 1)
