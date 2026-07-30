from django.contrib import admin

from .models import AirQualityAssessment, QuickCheck


@admin.register(QuickCheck)
class QuickCheckAdmin(admin.ModelAdmin):
    list_display = ("id", "observed_at", "temperature", "humidity", "pressure")

    @admin.display
    def observed_at(self, obj):
        return obj.value.observed_at

    @admin.display
    def temperature(self, obj):
        return f"{obj.value.temperature_c:.2f} °C"

    @admin.display
    def humidity(self, obj):
        return f"{obj.value.relative_humidity:.2f}%"

    @admin.display
    def pressure(self, obj):
        return f"{obj.value.pressure_hpa:.2f} hPa"


@admin.register(AirQualityAssessment)
class AirQualityAssessmentAdmin(admin.ModelAdmin):
    list_display = ("id", "observed_at", "percentage", "valid")

    @admin.display
    def observed_at(self, obj):
        return obj.value.observed_at

    @admin.display
    def percentage(self, obj):
        return f"{obj.value.percentage}%"

    @admin.display(boolean=True)
    def valid(self, obj):
        return obj.value.valid
