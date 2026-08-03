"""Opt-in tests for the physical BME690 attached to piagara."""

import os
from unittest import TestCase, skipUnless

from django.conf import settings

from .bme690_sensor import PimoroniBME690


HARDWARE_TESTS = os.environ.get("BME690_HARDWARE_TESTS") == "1"


@skipUnless(HARDWARE_TESTS, "set BME690_HARDWARE_TESTS=1 on piagara")
class BME690HardwareTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sensor = PimoroniBME690(address=settings.BME690_I2C_ADDRESS)

    def test_chip_and_variant_identify_as_bme690(self):
        """Confirm deployment is connected to the expected BME690 hardware."""
        import bme690

        self.assertEqual(self.sensor.sensor.chip_id, bme690.CHIP_ID)
        self.assertEqual(
            self.sensor.sensor._variant,
            0x02,
            "Bosch documents BME690 as variant ID 0x02",
        )

    def test_compensated_environmental_reading_is_in_operating_range(self):
        """Detect communication or compensation failures in a physical reading."""
        reading = self.sensor.read()
        self.assertGreaterEqual(reading.temperature_c, -40)
        self.assertLessEqual(reading.temperature_c, 85)
        self.assertGreaterEqual(reading.pressure_hpa, 300)
        self.assertLessEqual(reading.pressure_hpa, 1100)
        self.assertGreaterEqual(reading.relative_humidity, 0)
        self.assertLessEqual(reading.relative_humidity, 100)

    def test_repeated_readings_produce_a_robust_average(self):
        """Exercise the complete deployed sampling path against the physical sensor."""
        average = self.sensor.collect_average(
            samples=settings.BME690_SAMPLES_PER_OBSERVATION,
            sample_interval=settings.BME690_SAMPLE_INTERVAL,
            outlier_threshold=settings.BME690_OUTLIER_THRESHOLD,
        )
        self.assertGreaterEqual(average.retained_samples, 3)
        self.assertEqual(
            average.retained_samples + average.rejected_samples,
            settings.BME690_SAMPLES_PER_OBSERVATION,
        )
