"""Routes WebSocket (temps réel)."""
from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/notifications/', consumers.NotificationConsumer.as_asgi()),
    path('ws/incidents/<uuid:incident_id>/discussion/', consumers.DiscussionConsumer.as_asgi()),
    path('ws/incidents/<uuid:incident_id>/tasks/', consumers.TaskConsumer.as_asgi()),
    path('ws/collaborations/', consumers.CollaborationConsumer.as_asgi()),
    path('ws/activity-feed/', consumers.ActivityFeedConsumer.as_asgi()),
]
