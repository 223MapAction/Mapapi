"""IncidentTask endpoints: CRUD + actions complete / fail."""
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

from ..models import Incident, IncidentTask, TASK_PENDING, TASK_DONE, TASK_FAILED, Collaboration
from ..serializer import IncidentTaskSerializer
from ..permissions import IsIncidentLeader, IsIncidentLeaderOrContributor


@extend_schema_view(
    get=extend_schema(
        tags=['Tâches'],
        operation_id='tasks_list',
        summary="Lister les tâches d'un incident",
        description=(
            "Liste les tâches de l'incident, triées par date de début. Réservé au "
            "leader ou à un collaborateur accepté (`IsIncidentLeaderOrContributor`)."
        ),
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
        ],
        responses={
            200: IncidentTaskSerializer(many=True),
            403: OpenApiResponse(description="Ni leader ni contributeur de l'incident."),
        },
    ),
    post=extend_schema(
        tags=['Tâches'],
        operation_id='tasks_create',
        summary="Créer une tâche",
        description=(
            "Crée une tâche sur l'incident. Réservé au leader ou à un contributeur "
            "(`IsIncidentLeaderOrContributor`). `created_by` est renseigné automatiquement ; "
            "une tâche créée par le leader est auto-confirmée. Refusé si l'incident est clôturé."
        ),
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
        ],
        request=IncidentTaskSerializer,
        responses={
            201: IncidentTaskSerializer,
            400: OpenApiResponse(description="Données invalides ou incident clôturé."),
            403: OpenApiResponse(description="Ni leader ni contributeur de l'incident."),
        },
    ),
)
class IncidentTaskListCreateView(generics.ListCreateAPIView):
    """
    GET  /incidents/<incident_id>/tasks/  — liste des tâches (collaborateurs acceptés)
    POST /incidents/<incident_id>/tasks/  — créer une tâche (leader ou contributeur)
    """
    serializer_class = IncidentTaskSerializer
    permission_classes = [IsAuthenticated, IsIncidentLeaderOrContributor]

    def get_queryset(self):
        return IncidentTask.objects.filter(
            incident_id=self.kwargs['incident_id']
        ).order_by('start_date', 'id')

    def perform_create(self, serializer):
        incident = Incident.objects.get(pk=self.kwargs['incident_id'])
        if not incident.can_add_task():
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Impossible d'ajouter une tâche : l'incident est clôturé.")
        serializer.save(
            incident=incident,
            created_by=self.request.user,
        )


@extend_schema_view(post=extend_schema(
    tags=['Tâches'],
    operation_id='tasks_confirm',
    summary="Confirmer une tâche (leader)",
    description=(
        "Confirme une tâche créée par un contributeur (`is_confirmed=True`). Seules les "
        "tâches confirmées comptent dans la progression de l'incident. Réservé au leader "
        "(`IsIncidentLeader`)."
    ),
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de la tâche."),
    ],
    request=None,
    responses={
        200: IncidentTaskSerializer,
        404: OpenApiResponse(description="Tâche non trouvée."),
    },
))
class IncidentTaskConfirmView(APIView):
    """POST /incidents/<incident_id>/tasks/<pk>/confirm/"""
    permission_classes = [IsAuthenticated, IsIncidentLeader]

    def post(self, request, incident_id, pk):
        try:
            task = IncidentTask.objects.get(pk=pk, incident_id=incident_id)
        except IncidentTask.DoesNotExist:
            return Response({"error": "Tâche non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        task.is_confirmed = True
        task.save()  # le save() déclenche incident.update_progress()

        serializer = IncidentTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        tags=['Tâches'],
        operation_id='tasks_retrieve',
        summary="Détail d'une tâche",
        description="Détail d'une tâche. Accessible à tout collaborateur accepté de l'incident.",
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de la tâche."),
        ],
        responses={
            200: IncidentTaskSerializer,
            404: OpenApiResponse(description="Tâche non trouvée."),
        },
    ),
    put=extend_schema(
        tags=['Tâches'],
        operation_id='tasks_update',
        summary="Modifier une tâche",
        description=(
            "Remplace une tâche (PUT). Accessible au leader OU à un contributeur accepté "
            "(`IsIncidentLeaderOrContributor`) ; lecture seule pour les observateurs. Refusé "
            "si l'incident est clôturé."
        ),
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de la tâche."),
        ],
        request=IncidentTaskSerializer,
        responses={
            200: IncidentTaskSerializer,
            400: OpenApiResponse(description="Données invalides ou incident clôturé."),
            403: OpenApiResponse(description="Permission refusée (non leader)."),
            404: OpenApiResponse(description="Tâche non trouvée."),
        },
    ),
    patch=extend_schema(
        tags=['Tâches'],
        operation_id='tasks_partial_update',
        summary="Modifier partiellement une tâche",
        description=(
            "Modification partielle d'une tâche (PATCH). Accessible au leader OU à un "
            "contributeur accepté (`IsIncidentLeaderOrContributor`) ; lecture seule pour "
            "les observateurs."
        ),
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de la tâche."),
        ],
        request=IncidentTaskSerializer,
        responses={
            200: IncidentTaskSerializer,
            400: OpenApiResponse(description="Données invalides ou incident clôturé."),
            403: OpenApiResponse(description="Permission refusée (non leader)."),
            404: OpenApiResponse(description="Tâche non trouvée."),
        },
    ),
    delete=extend_schema(
        tags=['Tâches'],
        operation_id='tasks_destroy',
        summary="Supprimer une tâche",
        description="Supprime une tâche. Accessible au leader OU à un contributeur accepté (`IsIncidentLeaderOrContributor`).",
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de la tâche."),
        ],
        responses={
            204: OpenApiResponse(description="Tâche supprimée."),
            403: OpenApiResponse(description="Permission refusée (non leader)."),
            404: OpenApiResponse(description="Tâche non trouvée."),
        },
    ),
)
class IncidentTaskDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /incidents/<incident_id>/tasks/<pk>/  — détail (tout collaborateur accepté)
    PUT    /incidents/<incident_id>/tasks/<pk>/  — modifier (leader ou contributeur)
    PATCH  /incidents/<incident_id>/tasks/<pk>/  — modifier partiel (leader ou contributeur)
    DELETE /incidents/<incident_id>/tasks/<pk>/  — supprimer (leader ou contributeur)
    """
    serializer_class = IncidentTaskSerializer
    # Leader OU contributeur accepté peut modifier/supprimer (cohérent avec la création
    # et la complétion). Les observateurs gardent un accès en lecture seule.
    permission_classes = [IsAuthenticated, IsIncidentLeaderOrContributor]

    def get_queryset(self):
        return IncidentTask.objects.filter(
            incident_id=self.kwargs['incident_id']
        )


@extend_schema_view(post=extend_schema(
    tags=['Tâches'],
    operation_id='tasks_complete',
    summary="Marquer une tâche terminée",
    description=(
        "Passe la tâche à l'état `done`. Au moins une preuve est requise "
        "(`proof_image` ou `proof_video`), envoyée en `multipart/form-data`. Accessible au "
        "leader OU à un contributeur accepté (`IsIncidentLeaderOrContributor`) — celui qui "
        "fait le travail peut fournir la preuve. Déclenche le recalcul de la progression."
    ),
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de la tâche."),
    ],
    request=inline_serializer(
        name='TaskCompleteRequest',
        fields={
            'proof_image': serializers.ImageField(required=False),
            'proof_video': serializers.FileField(required=False),
        },
    ),
    responses={
        200: IncidentTaskSerializer,
        400: OpenApiResponse(description="Aucune preuve fournie (proof_image ou proof_video requis)."),
        404: OpenApiResponse(description="Tâche non trouvée."),
    },
))
class IncidentTaskCompleteView(APIView):
    """POST /incidents/<incident_id>/tasks/<pk>/complete/"""
    # Leader OU contributeur accepté : un collaborateur qui fait le travail peut
    # marquer la tâche terminée en uploadant une preuve. Le leader garde la main via
    # la confirmation (`is_confirmed`) qui gouverne la progression de l'incident.
    permission_classes = [IsAuthenticated, IsIncidentLeaderOrContributor]

    def post(self, request, incident_id, pk):
        try:
            task = IncidentTask.objects.get(pk=pk, incident_id=incident_id)
        except IncidentTask.DoesNotExist:
            return Response({"error": "Tâche non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        # On accepte proof_image / proof_video dans request.data ou request.FILES
        proof_image = request.FILES.get('proof_image') or request.data.get('proof_image')
        proof_video = request.FILES.get('proof_video') or request.data.get('proof_video')

        if not proof_image and not proof_video:
            return Response(
                {"error": "Une tâche terminée doit fournir une preuve (proof_image ou proof_video)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task.state = TASK_DONE
        if proof_image:
            task.proof_image = proof_image
        if proof_video:
            task.proof_video = proof_video
        task.save()  # le save() déclenche incident.update_progress()

        serializer = IncidentTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(post=extend_schema(
    tags=['Tâches'],
    operation_id='tasks_fail',
    summary="Marquer une tâche échouée",
    description=(
        "Passe la tâche à l'état `failed`. Un motif `failure_reason` est requis. Accessible "
        "au leader OU à un contributeur accepté (`IsIncidentLeaderOrContributor`). "
        "Déclenche le recalcul de la progression de l'incident."
    ),
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
        OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de la tâche."),
    ],
    request=inline_serializer(
        name='TaskFailRequest',
        fields={'failure_reason': serializers.CharField()},
    ),
    responses={
        200: IncidentTaskSerializer,
        400: OpenApiResponse(description="Motif d'échec (failure_reason) manquant."),
        404: OpenApiResponse(description="Tâche non trouvée."),
    },
    examples=[
        OpenApiExample('Motif', value={'failure_reason': "Accès au site impossible"},
                       request_only=True),
    ],
))
class IncidentTaskFailView(APIView):
    """POST /incidents/<incident_id>/tasks/<pk>/fail/"""
    # Leader OU contributeur accepté (idem complete : celui qui fait le travail peut
    # signaler l'échec avec un motif).
    permission_classes = [IsAuthenticated, IsIncidentLeaderOrContributor]

    def post(self, request, incident_id, pk):
        try:
            task = IncidentTask.objects.get(pk=pk, incident_id=incident_id)
        except IncidentTask.DoesNotExist:
            return Response({"error": "Tâche non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        failure_reason = request.data.get('failure_reason')
        if not failure_reason:
            return Response(
                {"error": "Un motif d'échec (failure_reason) est requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task.state = TASK_FAILED
        task.failure_reason = failure_reason
        task.save()  # le save() déclenche incident.update_progress()

        serializer = IncidentTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(post=extend_schema(
    tags=['Tâches'],
    operation_id='tasks_relaunch',
    summary="Relancer une tâche échouée",
    description=(
        "Relance une tâche en état `failed` (spec D11) : la repasse en `pending` (À faire) "
        "tout en CONSERVANT le motif d'échec (`failure_reason`). Réservé au leader "
        "(`IsIncidentLeader`). Déclenche le recalcul de la progression de l'incident."
    ),
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
        OpenApiParameter('task_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de la tâche."),
    ],
    request=None,
    responses={
        200: IncidentTaskSerializer,
        400: OpenApiResponse(description="La tâche n'est pas en échec (seul `failed` est relançable)."),
        404: OpenApiResponse(description="Tâche non trouvée."),
    },
))
class IncidentTaskRelaunchView(APIView):
    """POST /incidents/<incident_id>/tasks/<task_id>/relaunch/"""
    permission_classes = [IsAuthenticated, IsIncidentLeader]

    def post(self, request, incident_id, task_id):
        try:
            task = IncidentTask.objects.get(pk=task_id, incident_id=incident_id)
        except IncidentTask.DoesNotExist:
            return Response({"error": "Tâche non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        if task.state != TASK_FAILED:
            return Response(
                {"error": "Seule une tâche échouée (failed) peut être relancée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Repasse en 'pending' ; le motif d'échec est volontairement CONSERVÉ (spec D11).
        task.state = TASK_PENDING
        task.save()  # le save() déclenche incident.update_progress()

        serializer = IncidentTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_200_OK)
