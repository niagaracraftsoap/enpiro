from django.urls import path

from . import views

app_name = "measurements"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/readings/latest/", views.latest_reading, name="latest-reading"),
    path("api/readings/history/", views.reading_history, name="reading-history"),
    path(
        "api/readings/history.csv",
        views.reading_history_csv,
        name="reading-history-csv",
    ),
    path("api/readings/reset/", views.reset_readings, name="reset-readings"),
]
