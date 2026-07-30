from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from .semantic import (
    AssessmentCheck,
    create_air_quality_assessment,
    create_environmental_observation,
    decode_air_quality_assessment,
    decode_environmental_observation,
)


def broadcast(value):
    async_to_sync(get_channel_layer().group_send)(
        "environmental_readings",
        {"type": "reading.created", "reading": value.as_dict()},
    )


def save_environmental_observation(
    *,
    observed_at=None,
    temperature_c,
    relative_humidity,
    pressure_hpa,
):
    term = create_environmental_observation(
        observed_at or timezone.now(),
        temperature_c,
        relative_humidity,
        pressure_hpa,
    )
    broadcast(decode_environmental_observation(term))
    return term


def save_air_quality_assessment(
    *,
    observed_at=None,
    percentage,
    check=AssessmentCheck(0),
):
    term = create_air_quality_assessment(
        observed_at or timezone.now(),
        percentage,
        check,
    )
    broadcast(decode_air_quality_assessment(term))
    return term
