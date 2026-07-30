from django.urls import path

from . import views

app_name = "measurements"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/readings/latest/", views.latest_reading, name="latest-reading"),
]

