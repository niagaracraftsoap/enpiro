from .models import AirQualityAssessment, EnvironmentalObservation


def _recent_values(model, limit):
    terms = list(model.objects.order_by("-pk")[:limit])
    return [term.value for term in reversed(terms)]


def environmental_history(limit=48):
    return _recent_values(EnvironmentalObservation, limit)


def assessment_history(limit=48):
    return _recent_values(AirQualityAssessment, limit)


def latest_environmental_observation():
    term = EnvironmentalObservation.objects.order_by("-pk").first()
    return term.value if term else None


def latest_air_quality_assessment():
    term = AirQualityAssessment.objects.order_by("-pk").first()
    return term.value if term else None
