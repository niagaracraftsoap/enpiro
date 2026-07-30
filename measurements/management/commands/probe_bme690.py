from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Probe I2C addresses 0x76/0x77 and identify a BME690 variant."

    def add_arguments(self, parser):
        parser.add_argument("--bus", type=int, default=1)

    def handle(self, *args, **options):
        try:
            from smbus2 import SMBus
        except ImportError as error:
            raise CommandError("smbus2 is not installed; run pip install -r requirements.txt") from error

        found = False
        try:
            with SMBus(options["bus"]) as bus:
                for address in (0x76, 0x77):
                    try:
                        chip_id = bus.read_byte_data(address, 0xD0)
                        variant_id = bus.read_byte_data(address, 0xF0)
                    except OSError:
                        continue
                    found = True
                    label = "BME690" if variant_id == 0x02 else "unknown BME68x variant"
                    self.stdout.write(
                        f"0x{address:02x}: chip ID 0x{chip_id:02x}, "
                        f"variant ID 0x{variant_id:02x} ({label})"
                    )
        except (FileNotFoundError, PermissionError, OSError) as error:
            raise CommandError(
                f"Cannot open I2C bus {options['bus']}: {error}. "
                "Enable I2C and ensure this user belongs to the i2c group."
            ) from error

        if not found:
            raise CommandError("No device responded at 0x76 or 0x77.")
