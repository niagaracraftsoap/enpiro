import csv
import secrets
from datetime import datetime, time, timedelta

from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .repository import (
    environmental_history,
    environmental_history_iterator,
    latest_environmental_observation,
)
from .services import reset_dataset

METRICS = {
    "temperature_c": ("Temperature", "°C"),
    "relative_humidity": ("Relative humidity", "%"),
    "pressure_hpa": ("Pressure", "hPa"),
}
RESET_PASSWORD = "hardcodedresetpassword"


class _CsvStream:
    """Give csv.writer the file-like interface expected by StreamingHttpResponse."""

    @staticmethod
    def write(value):
        return value


def _parse_range(request):
    zone = timezone.get_current_timezone()

    def parse(name, *, end=False):
        raw = request.GET.get(name)
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(raw)
        except ValueError as error:
            raise ValueError(f"Invalid {name} date or time.") from error
        if value.tzinfo is None:
            if len(raw) == 10:
                value = datetime.combine(
                    value.date(),
                    time.max if end else time.min,
                )
            value = timezone.make_aware(value, zone)
        return value

    start = parse("start")
    end = parse("end", end=True)
    if start and end and start > end:
        raise ValueError("Start must be before end.")
    return start, end


def _history_response(request, *, csv_export=False):
    metric = request.GET.get("metric", "temperature_c")
    bundled = not csv_export and metric == "all"
    if not csv_export and metric not in METRICS and not bundled:
        return JsonResponse({"detail": "Unknown metric."}, status=400)
    if csv_export:
        requested = request.GET.get("metrics", metric)
        metrics = list(METRICS) if requested == "all" else requested.split(",")
        metrics = list(dict.fromkeys(metrics))
        if not metrics or any(item not in METRICS for item in metrics):
            return JsonResponse({"detail": "Unknown metric selection."}, status=400)
    try:
        start, end = _parse_range(request)
    except ValueError as error:
        return JsonResponse({"detail": str(error)}, status=400)

    if not csv_export:
        retention_start = timezone.now() - timedelta(
            days=settings.INTERFACE_HISTORY_RETENTION_DAYS
        )
        if end is not None and end < retention_start:
            return JsonResponse(
                {
                    "detail": (
                        "Interactive history is limited to the most recent "
                        f"{settings.INTERFACE_HISTORY_RETENTION_DAYS} days. "
                        "Use CSV export for older data."
                    )
                },
                status=400,
            )
        start = retention_start if start is None else max(start, retention_start)

    if csv_export:
        def rows():
            writer = csv.writer(_CsvStream())
            yield writer.writerow(("recorded_at", *metrics))
            for value in environmental_history_iterator(start=start, end=end):
                yield writer.writerow(
                    (
                        value.observed_at.isoformat(),
                        *(getattr(value, item) for item in metrics),
                    )
                )

        response = StreamingHttpResponse(rows(), content_type="text/csv")
        name = "environment" if len(metrics) > 1 else metrics[0]
        response["Content-Disposition"] = (
            f'attachment; filename="warehouse-{name}-history.csv"'
        )
        response["X-Accel-Buffering"] = "no"
        return response

    values = environmental_history(limit=None, start=start, end=end)
    if bundled:
        return JsonResponse(
            {
                "metrics": list(METRICS),
                "readings": [value.as_dict() for value in values],
            }
        )

    label, unit = METRICS[metric]
    return JsonResponse(
        {
            "metric": metric,
            "label": label,
            "unit": unit,
            "readings": [
                {
                    "recorded_at": value.observed_at.isoformat(),
                    "value": getattr(value, metric),
                }
                for value in values
            ],
        }
    )


def dashboard(request):
    environment = environmental_history()
    return render(
        request,
        "measurements/dashboard.html",
        {
            "latest_environment": environment[-1] if environment else None,
            "reading_history": [value.as_dict() for value in environment],
            "condition_thresholds": settings.WAREHOUSE_CONDITION_THRESHOLDS,
        },
    )


def latest_reading(request):
    environment = latest_environmental_observation()
    if environment is None:
        return JsonResponse({"detail": "No readings have been recorded yet."}, status=404)
    return JsonResponse({"environment": environment.as_dict()})


def reading_history(request):
    return _history_response(request)


def reading_history_csv(request):
    return _history_response(request, csv_export=True)


@require_POST
def reset_readings(request):
    if (
        request.POST.get("acknowledge_export") != "yes"
        or request.POST.get("confirmation") != "RESET"
        or not secrets.compare_digest(
            request.POST.get("password", ""),
            RESET_PASSWORD,
        )
    ):
        return JsonResponse(
            {"detail": "The reset confirmation or password is incorrect."},
            status=400,
        )

    terms_deleted, symbols_deleted = reset_dataset()
    return JsonResponse(
        {
            "terms_deleted": terms_deleted,
            "symbols_deleted": symbols_deleted,
        }
    )
