"""PartnerSuggestion endpoints: CRUD + actions accept / reject."""
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from ..models import (
    Incident, PartnerSuggestion, Collaboration,
    SUGGESTION_PENDING, SUGGESTION_ACCEPTED, SUGGESTION_REJECTED,
)
from ..serializer import PartnerSuggestionSerializer
from ..permissions import (
    IsIncidentCollaborator, IsIncidentContributor, IsIncidentLeader,
    IsIncidentLeaderOrContributor,
)


class PartnerSuggestionListCreateView(generics.ListCreateAPIView):
    """
    GET  /incidents/<incident_id>/suggestions/  — liste (tous collaborateurs)
    POST /incidents/<incident_id>/suggestions/  — créer (leader OU contributeurs)
    """
    serializer_class = PartnerSuggestionSerializer
    permission_classes = [IsAuthenticated, IsIncidentLeaderOrContributor]

    def get_queryset(self):
        return PartnerSuggestion.objects.filter(
            incident_id=self.kwargs['incident_id']
        )

    def perform_create(self, serializer):
        incident = Incident.objects.get(pk=self.kwargs['incident_id'])
        if not incident.can_suggest_partner():
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                "Impossible de suggérer un partenaire : l'incident est clôturé."
            )
        serializer.save(
            incident=incident,
            suggested_by=self.request.user,
        )


class PartnerSuggestionDetailView(generics.RetrieveAPIView):
    """
    GET /incidents/<incident_id>/suggestions/<pk>/  — détail
    """
    serializer_class = PartnerSuggestionSerializer
    permission_classes = [IsAuthenticated, IsIncidentCollaborator]

    def get_queryset(self):
        return PartnerSuggestion.objects.filter(
            incident_id=self.kwargs['incident_id']
        )


@extend_schema(
    description="Accepter une suggestion de partenaire. Crée une Collaboration accepted avec le rôle suggéré.",
    responses={200: PartnerSuggestionSerializer},
)
class PartnerSuggestionAcceptView(APIView):
    """POST /incidents/<incident_id>/suggestions/<pk>/accept/"""
    permission_classes = [IsAuthenticated, IsIncidentLeader]

    def post(self, request, incident_id, pk):
        try:
            suggestion = PartnerSuggestion.objects.get(
                pk=pk, incident_id=incident_id
            )
        except PartnerSuggestion.DoesNotExist:
            return Response(
                {"error": "Suggestion non trouvée."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if suggestion.status != SUGGESTION_PENDING:
            return Response(
                {"error": f"Cette suggestion est déjà {suggestion.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Créer la Collaboration accepted avec le rôle suggéré
        collaboration, created = Collaboration.objects.get_or_create(
            incident_id=incident_id,
            user=suggestion.suggested_partner,
            defaults={
                'role': suggestion.suggested_role,
                'status': 'accepted',
            },
        )
        if not created:
            # La collaboration existait déjà (par ex. pending) → on la met à jour
            collaboration.role = suggestion.suggested_role
            collaboration.status = 'accepted'
            collaboration.save()

        suggestion.status = SUGGESTION_ACCEPTED
        suggestion.save()

        serializer = PartnerSuggestionSerializer(suggestion)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    description="Rejeter une suggestion de partenaire.",
    responses={200: PartnerSuggestionSerializer},
)
class PartnerSuggestionRejectView(APIView):
    """POST /incidents/<incident_id>/suggestions/<pk>/reject/"""
    permission_classes = [IsAuthenticated, IsIncidentLeader]

    def post(self, request, incident_id, pk):
        try:
            suggestion = PartnerSuggestion.objects.get(
                pk=pk, incident_id=incident_id
            )
        except PartnerSuggestion.DoesNotExist:
            return Response(
                {"error": "Suggestion non trouvée."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if suggestion.status != SUGGESTION_PENDING:
            return Response(
                {"error": f"Cette suggestion est déjà {suggestion.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suggestion.status = SUGGESTION_REJECTED
        suggestion.save()

        serializer = PartnerSuggestionSerializer(suggestion)
        return Response(serializer.data, status=status.HTTP_200_OK)
