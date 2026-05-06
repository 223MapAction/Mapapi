"""Prediction & chat history endpoints."""
import json

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status, generics
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema(
    description="Endpoint for retrieving all predictions",
    responses={200: PredictionSerializer(many=True)},
) 
class PredictionView(generics.ListAPIView):
    permission_classes = ()
    queryset = Prediction.objects.all()
    serializer_class = PredictionSerializer

def history_list(request):
    histories = ChatHistory.objects.all()  # Retrieve all history records
    data = {"histories": list(histories.values("session_id", "question", "answer"))}
    return JsonResponse(data)

@csrf_exempt  # Disable CSRF token for this view for simplicity
def add_history(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            history = ChatHistory(
                user_id=data['session_id'],
                question=data['question'],
                answer=data['answer']
            )
            history.save()
            return JsonResponse({"message": "History added successfully!"}, status=201)
        except (KeyError, TypeError) as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return HttpResponse(status=405)  # Method Not Allowed
class PredictionViewByID(generics.ListAPIView):
    permission_classes = ()
    serializer_class = PredictionSerializer

    def get_queryset(self):
        prediction_id = self.kwargs['id']
        queryset = Prediction.objects.filter(prediction_id=prediction_id)
        return queryset
class PredictionViewByIncidentID(generics.ListAPIView):
    permission_classes = ()
    serializer_class = PredictionSerializer

    def get_queryset(self):
        incident_id = self.kwargs['id']
        queryset = Prediction.objects.filter(incident_id=incident_id)
        return queryset
class ChatHistoryViewByIncident(generics.ListAPIView):
    permission_classes = ()
    serializer_class = ChatHistorySerializer

    def get_queryset(self):
        session_id = self.kwargs['id']
        queryset = ChatHistory.objects.filter(session_id=session_id)
        return queryset
