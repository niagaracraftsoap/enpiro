from django.conf import settings
from django.core.checks import Error, register


@register()
def check_condition_thresholds(app_configs, **kwargs):
    errors = []
    thresholds = settings.WAREHOUSE_CONDITION_THRESHOLDS
    for metric in ("temperature_c", "relative_humidity"):
        limits = thresholds.get(metric, {})
        try:
            ordered = (
                float(limits["red_min"]),
                float(limits["green_min"]),
                float(limits["green_max"]),
                float(limits["red_max"]),
            )
        except (KeyError, TypeError, ValueError):
            ordered = ()
        if len(ordered) != 4 or not (
            ordered[0] < ordered[1] <= ordered[2] < ordered[3]
        ):
            errors.append(
                Error(
                    f"Invalid warehouse condition thresholds for {metric}.",
                    hint="Require red_min < green_min <= green_max < red_max.",
                    id="measurements.E001",
                )
            )
    return errors
