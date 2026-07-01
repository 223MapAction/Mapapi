"""PartnerSuggestion endpoints: CRUD + actions accept / reject."""
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse,
    OpenApiExample, inline_serializer,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers

from ..models import (
    Incident, PartnerSuggestion, Collaboration,
    SUGGESTION_PENDING, SUGGESTION_ACCEPTED, SUGGESTION_REJECTED,
)
from ..serializer import PartnerSuggestionSerializer
from ..permissions import (
    IsIncidentCollaborator, IsIncidentContributor, IsIncidentLeader,
    IsIncidentLeaderOrContributor,
)


@extend_schema_view(get=extend_schema(
    tags=['Suggestions de partenaires'],
    operation_id='suggestions_received_list',
    summary="Mes suggestions reçues",
    description=(
        "Liste les suggestions de partenariat où l'utilisateur connecté est le partenaire "
        "proposé, triées par date décroissante. Authentification requise."
    ),
    parameters=[
        OpenApiParameter('status', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         enum=['pending', 'accepted', 'rejected'],
                         description="Filtre optionnel sur le statut de la suggestion."),
    ],
    responses={200: PartnerSuggestionSerializer(many=True)},
))
class MyReceivedSuggestionsView(generics.ListAPIView):
    """
    GET /my-suggestions/received/  — Liste les suggestions où JE suis le partenaire proposé.

    Filtre optionnel via ?status=pending|accepted|rejected.
    L'utilisateur peut ensuite décider d'accepter/refuser via les endpoints
    /incidents/<id>/suggestions/<pk>/accept|reject/ (s'il est leader de
    l'incident concerné).
    """
    serializer_class = PartnerSuggestionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = PartnerSuggestion.objects.filter(
            suggested_partner=self.request.user
        ).select_related('incident', 'suggested_by').order_by('-created_at')
        status_param = self.request.query_params.get('status')
        if status_param in (SUGGESTION_PENDING, SUGGESTION_ACCEPTED, SUGGESTION_REJECTED):
            qs = qs.filter(status=status_param)
        return qs


@extend_schema_view(get=extend_schema(
    tags=['Suggestions de partenaires'],
    operation_id='suggestions_sent_list',
    summary="Mes suggestions envoyées",
    description=(
        "Liste les suggestions de partenariat créées par l'utilisateur connecté, triées par "
        "date décroissante. Authentification requise."
    ),
    parameters=[
        OpenApiParameter('status', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         enum=['pending', 'accepted', 'rejected'],
                         description="Filtre optionnel sur le statut de la suggestion."),
    ],
    responses={200: PartnerSuggestionSerializer(many=True)},
))
class MySentSuggestionsView(generics.ListAPIView):
    """
    GET /my-suggestions/sent/  — Liste les suggestions QUE J'AI faites.

    Filtre optionnel via ?status=pending|accepted|rejected.
    """
    serializer_class = PartnerSuggestionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = PartnerSuggestion.objects.filter(
            suggested_by=self.request.user
        ).select_related('incident', 'suggested_partner').order_by('-created_at')
        status_param = self.request.query_params.get('status')
        if status_param in (SUGGESTION_PENDING, SUGGESTION_ACCEPTED, SUGGESTION_REJECTED):
            qs = qs.filter(status=status_param)
        return qs


@extend_schema_view(
    get=extend_schema(
        tags=['Suggestions de partenaires'],
        operation_id='suggestions_list',
        summary="Lister les suggestions d'un incident",
        description=(
            "Liste les suggestions de partenariat de l'incident. Réservé au leader ou à un "
            "contributeur (`IsIncidentLeaderOrContributor`)."
        ),
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
            OpenApiParameter('status', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                             enum=['pending', 'accepted', 'rejected'],
                             description="Filtre optionnel sur le statut de la suggestion."),
        ],
        responses={
            200: PartnerSuggestionSerializer(many=True),
            403: OpenApiResponse(description="Ni leader ni contributeur de l'incident."),
        },
    ),
    post=extend_schema(
        tags=['Suggestions de partenaires'],
        operation_id='suggestions_create',
        summary="Créer une suggestion de partenaire",
        description=(
            "Crée une suggestion de partenariat sur l'incident. Réservé au leader ou à un "
            "contributeur (`IsIncidentLeaderOrContributor`). `suggested_by` est renseigné "
            "automatiquement. Envoyer soit `suggested_partner` (User), soit "
            "`suggested_organisation` (org résolue vers son admin/bureau). Refusé si l'incident "
            "est clôturé."
        ),
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
        ],
        request=PartnerSuggestionSerializer,
        responses={
            201: PartnerSuggestionSerializer,
            400: OpenApiResponse(description="Données invalides ou incident clôturé."),
            403: OpenApiResponse(description="Ni leader ni contributeur de l'incident."),
        },
        examples=[
            OpenApiExample(
                'Suggestion via organisation',
                value={'suggested_organisation': '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                       'suggested_role': 'contributor',
                       'justification': "Expertise locale pertinente"},
                request_only=True,
            ),
        ],
    ),
)
class PartnerSuggestionListCreateView(generics.ListCreateAPIView):
    """
    GET  /incidents/<incident_id>/suggestions/  — liste (tous collaborateurs)
    POST /incidents/<incident_id>/suggestions/  — créer (leader OU contributeurs)
    """
    serializer_class = PartnerSuggestionSerializer
    permission_classes = [IsAuthenticated, IsIncidentLeaderOrContributor]

    def get_queryset(self):
        qs = PartnerSuggestion.objects.filter(
            incident_id=self.kwargs['incident_id']
        ).select_related('incident', 'suggested_by', 'suggested_partner')
        status_param = self.request.query_params.get('status')
        if status_param in (SUGGESTION_PENDING, SUGGESTION_ACCEPTED, SUGGESTION_REJECTED):
            qs = qs.filter(status=status_param)
        return qs

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


@extend_schema_view(get=extend_schema(
    tags=['Suggestions de partenaires'],
    operation_id='suggestions_retrieve',
    summary="Détail d'une suggestion",
    description=(
        "Détail d'une suggestion de partenariat. Accessible à tout collaborateur de "
        "l'incident (`IsIncidentCollaborator`)."
    ),
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de la suggestion."),
    ],
    responses={
        200: PartnerSuggestionSerializer,
        404: OpenApiResponse(description="Suggestion non trouvée."),
    },
))
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


@extend_schema_view(post=extend_schema(
    tags=['Suggestions de partenaires'],
    operation_id='suggestions_accept',
    summary="Accepter une suggestion",
    description=(
        "Accepte une suggestion en attente : crée (ou met à jour) une `Collaboration` "
        "`accepted` pour le partenaire avec le rôle suggéré, et passe la suggestion à "
        "`accepted`. Réservé au leader (`IsIncidentLeader`)."
    ),
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de la suggestion."),
    ],
    request=None,
    responses={
        200: PartnerSuggestionSerializer,
        400: OpenApiResponse(description="La suggestion n'est pas en attente (déjà traitée)."),
        404: OpenApiResponse(description="Suggestion non trouvée."),
    },
))
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


@extend_schema_view(post=extend_schema(
    tags=['Suggestions de partenaires'],
    operation_id='suggestions_reject',
    summary="Rejeter une suggestion",
    description=(
        "Rejette une suggestion en attente : la passe à `rejected`. Réservé au leader "
        "(`IsIncidentLeader`)."
    ),
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de la suggestion."),
    ],
    request=None,
    responses={
        200: PartnerSuggestionSerializer,
        400: OpenApiResponse(description="La suggestion n'est pas en attente (déjà traitée)."),
        404: OpenApiResponse(description="Suggestion non trouvée."),
    },
))
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
