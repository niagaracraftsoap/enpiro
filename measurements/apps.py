from django.apps import AppConfig


class MeasurementsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'measurements'

    def ready(self):
        from . import checks  # noqa: F401
