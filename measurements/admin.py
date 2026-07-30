from django.contrib import admin

from .models import QuickCheck


@admin.register(QuickCheck)
class QuickCheckAdmin(admin.ModelAdmin):
    list_display = ("id", "observed_at", "temperature", "humidity", "pressure")

    @admin.display
    def observed_at(self, obj):
        return obj.value.observed_at

    @admin.display
    def temperature(self, obj):
        return f"{obj.value.temperature_c:.1f} °C"

    @admin.display
    def humidity(self, obj):
        return f"{obj.value.relative_humidity:.1f}%"

    @admin.display
    def pressure(self, obj):
        return f"{obj.value.pressure_hpa:.0f} hPa"
