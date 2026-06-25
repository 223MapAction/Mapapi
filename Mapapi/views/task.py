"""IncidentTask endpoints: CRUD + actions complete / fail."""
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from ..models import Incident, IncidentTask, TASK_DONE, TASK_FAILED, Collaboration
from ..serializer import IncidentTaskSerializer
from ..permissions import IsIncidentLeaderOrReadOnlyCollaborator, IsIncidentLeader, IsIncidentCollaborator, IsIncidentLeaderOrContributor


class IncidentTaskListCreateView(generics.ListCreateAPIView):
    """
    GET  /incidents/<incident_id>/tasks/  — liste des tâches (collaborateurs acceptés)
    POST /incidents/<incident_id>/tasks/  — créer une tâche (leader ou contributeur)
    """
    serializer_class = IncidentTaskSerializer
    permission_classes = [IsAuthenticated, IsIncidentLeaderOrContributor]

    def get_queryset(self):
        incident_id = self.kwargs['incident_id']
        qs = IncidentTask.objects.filter(incident_id=incident_id).order_by('start_date', 'id')
        print(f"DEBUG: incident_id={incident_id}, tasks count={qs.count()}")
        if qs.count() > 0:
            print(f"DEBUG: task IDs = {list(qs.values_list('id', flat=True))}")
        return qs

    def perform_create(self, serializer):
        incident = Incident.objects.get(pk=self.kwargs['incident_id'])
        if not incident.can_add_task():
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Impossible d'ajouter une tâche : l'incident est clôturé.")
        serializer.save(
            incident=incident,
            created_by=self.request.user,
        )


@extend_schema(
    description="Confirmer une tâche créée par un contributeur (Leader uniquement).",
    responses={200: IncidentTaskSerializer},
)
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


class IncidentTaskDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /incidents/<incident_id>/tasks/<pk>/  — détail
    PUT    /incidents/<incident_id>/tasks/<pk>/  — modifier (leader)
    PATCH  /incidents/<incident_id>/tasks/<pk>/  — modifier partiel (leader)
    DELETE /incidents/<incident_id>/tasks/<pk>/  — supprimer (leader)
    """
    serializer_class = IncidentTaskSerializer
    permission_classes = [IsAuthenticated, IsIncidentLeaderOrReadOnlyCollaborator]

    def get_queryset(self):
        return IncidentTask.objects.filter(
            incident_id=self.kwargs['incident_id']
        )


@extend_schema(
    description="Marquer une tâche comme terminée (done). Requiert proof_image ou proof_video.",
    responses={200: IncidentTaskSerializer},
)
class IncidentTaskCompleteView(APIView):
    """POST /incidents/<incident_id>/tasks/<pk>/complete/

    Le leader OU un contributeur accepté peut marquer une tâche comme terminée.
    """
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


@extend_schema(
    description="Marquer une tâche comme échouée (failed). Requiert failure_reason.",
    responses={200: IncidentTaskSerializer},
)
class IncidentTaskFailView(APIView):
    """POST /incidents/<incident_id>/tasks/<pk>/fail/"""
    permission_classes = [IsAuthenticated, IsIncidentLeader]

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
