from django.urls import path

from .consumers import ReadingConsumer

websocket_urlpatterns = [
    path("ws/readings/", ReadingConsumer.as_asgi()),
]

