"""Prediction endpoints.

The legacy session-keyed chat-history endpoints (`history_list`, `add_history`,
`ChatHistoryViewByIncident`) were removed — they were unauthenticated, leaked all
chat rows, and used a spoofable client `session_id`. The incident AI chat is now
served by `IncidentChatView` (`incidents/<id>/chat/`), scoped to the user.
"""
from rest_framework import generics

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from ..serializer import *


@extend_schema_view(get=extend_schema(
    tags=['Prédiction & IA'],
    operation_id='predictions_list',
    summary="Lister toutes les prédictions",
    description="Retourne la liste de toutes les prédictions IA (`Prediction`). "
                "Endpoint public (aucune authentification requise).",
    responses={200: PredictionSerializer(many=True)},
))
class PredictionView(generics.ListAPIView):
    permission_classes = ()
    queryset = Prediction.objects.all()
    serializer_class = PredictionSerializer


@extend_schema_view(get=extend_schema(
    tags=['Prédiction & IA'],
    operation_id='predictions_retrieve',
    summary="Prédiction(s) par prediction_id",
    description="Retourne la/les prédiction(s) dont le champ `prediction_id` correspond "
                "à l'identifiant fourni (résultat sous forme de liste). Endpoint public.",
    parameters=[
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="prediction_id de la prédiction"),
    ],
    responses={200: PredictionSerializer(many=True)},
))
class PredictionViewByID(generics.ListAPIView):
    permission_classes = ()
    serializer_class = PredictionSerializer

    def get_queryset(self):
        prediction_id = self.kwargs['id']
        return Prediction.objects.filter(prediction_id=prediction_id)


@extend_schema_view(get=extend_schema(
    tags=['Prédiction & IA'],
    operation_id='predictions_by_incident',
    summary="Prédictions d'un incident",
    description="Retourne la/les prédiction(s) liée(s) à l'incident dont l'id est fourni "
                "(consommé par le frontend `getIncidentPredictionService`). Endpoint public.",
    parameters=[
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="id de l'incident"),
    ],
    responses={200: PredictionSerializer(many=True)},
))
class PredictionViewByIncidentID(generics.ListAPIView):
    permission_classes = ()
    serializer_class = PredictionSerializer

    def get_queryset(self):
        incident_id = self.kwargs['id']
        return Prediction.objects.filter(incident_id=incident_id)
