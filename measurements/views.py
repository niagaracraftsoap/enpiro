from django.http import JsonResponse
from django.shortcuts import render

from .repository import (
    assessment_history,
    environmental_history,
    latest_air_quality_assessment,
    latest_environmental_observation,
)


def dashboard(request):
    environment = environmental_history()
    assessments = assessment_history()
    return render(
        request,
        "measurements/dashboard.html",
        {
            "latest_environment": environment[-1] if environment else None,
            "latest_assessment": assessments[-1] if assessments else None,
            "reading_history": {
                "environment": [value.as_dict() for value in environment],
                "air_quality": [value.as_dict() for value in assessments],
            },
        },
    )


def latest_reading(request):
    environment = latest_environmental_observation()
    assessment = latest_air_quality_assessment()
    if environment is None and assessment is None:
        return JsonResponse({"detail": "No readings have been recorded yet."}, status=404)
    return JsonResponse(
        {
            "environment": environment.as_dict() if environment else None,
            "air_quality": assessment.as_dict() if assessment else None,
        }
    )
