"""Collaboration endpoints (request, accept, decline, handle, dashboard)."""
from django.db.models import Q, Count
from django.utils import timezone

from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from ..models import Collaboration, Incident, Notification, COLLAB_ROLE_LEADER
from ..serializer import CollaborationSerializer, CollaborationEnrichedSerializer
from ..Send_mails import send_email
from .common import CustomPageNumberPagination


@extend_schema(
    description="Vue dashboard des collaborations enrichies avec filtrage par statut, "
                "période et recherche textuelle.",
    responses={200: CollaborationEnrichedSerializer(many=True)},
)
class CollaborationDashboardView(generics.ListAPIView):
    """GET /collaborations/dashboard/

    Filtres query params :
      ?status=all|in-progress|completed|pending|accepted|declined
      ?date_from=YYYY-MM-DD  (end_date >= date_from)
      ?date_to=YYYY-MM-DD    (created_at <= date_to)
      ?search=texte           (titre incident, org, rôle, zone)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CollaborationEnrichedSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Collaboration.objects.filter(
            Q(user=user) | Q(incident__taken_by=user)
        ).select_related(
            'incident', 'user', 'user__organisation_member'
        ).order_by('-created_at')

        # --- Filtre par statut ---
        status_filter = self.request.query_params.get('status', 'all')
        status_map = {
            'in-progress': ['accepted'],
            'completed': ['accepted'],  # on filtre ensuite par etat incident
            'pending': ['pending'],
            'accepted': ['accepted'],
            'declined': ['declined'],
        }
        if status_filter in status_map:
            qs = qs.filter(status__in=status_map[status_filter])
        if status_filter == 'completed':
            qs = qs.filter(incident__etat='resolved')
        elif status_filter == 'in-progress':
            qs = qs.exclude(incident__etat='resolved')

        # --- Filtre par période ---
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(
                Q(end_date__gte=date_from) | Q(end_date__isnull=True)
            )
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        # --- Recherche textuelle ---
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(incident__title__icontains=search)
                | Q(user__organisation__icontains=search)
                | Q(user__organisation_member__name__icontains=search)
                | Q(role__icontains=search)
                | Q(incident__zone__icontains=search)
            )

        return qs


class CollaborationView(generics.CreateAPIView, generics.ListAPIView):
    """
    GET  /collaboration/  — liste des collaborations de l'utilisateur
    POST /collaboration/  — demander à rejoindre un incident (role=contributor|observer, status=pending)
    """
    permission_classes = [IsAuthenticated]
    queryset = Collaboration.objects.all()
    serializer_class = CollaborationSerializer

    def get_queryset(self):
        user = self.request.user
        return Collaboration.objects.filter(
            Q(user=user) | Q(incident__taken_by=user) 
        )

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            # Le rôle est validé par le serializer (pas de 'leader' autorisé)
            collaboration = serializer.save(user=request.user, status='pending')
            return Response(
                CollaborationSerializer(collaboration).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BulkCollaborationRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        requests_data = request.data.get('requests', [])
        if not isinstance(requests_data, list) or not requests_data:
            return Response({"error": "requests doit être une liste non vide."}, status=status.HTTP_400_BAD_REQUEST)

        created = []
        errors = []

        for index, item in enumerate(requests_data):
            incident_id = item.get('incident_id') or item.get('incident')
            if not incident_id:
                errors.append({"index": index, "error": "incident_id est requis."})
                continue

            try:
                Incident.objects.get(pk=incident_id)
            except Incident.DoesNotExist:
                errors.append({"index": index, "incident_id": incident_id, "error": "Incident non trouvé."})
                continue

            data = {
                "incident": incident_id,
                "role": item.get('role'),
                "motivation": item.get('motivation'),
                "end_date": item.get('end_date'),
            }
            serializer = CollaborationSerializer(data=data)
            if serializer.is_valid():
                collaboration = serializer.save(user=request.user, status='pending')
                created.append(CollaborationSerializer(collaboration).data)
            else:
                errors.append({"index": index, "incident_id": incident_id, "errors": serializer.errors})

        return Response({
            "created": created,
            "errors": errors,
            "message": f"{len(created)} demande(s) de collaboration créée(s)."
        }, status=status.HTTP_207_MULTI_STATUS if errors else status.HTTP_201_CREATED)


class HandleCollaborationRequestView(APIView):
    """POST /collaboration/<collaboration_id>/<action>/  (accept|reject)"""
    permission_classes = [IsAuthenticated]

    def post(self, request, collaboration_id, action, format=None):
        try:
            collaboration = Collaboration.objects.get(id=collaboration_id)
        except Collaboration.DoesNotExist:
            return Response({"error": "Collaboration not found"}, status=status.HTTP_404_NOT_FOUND)

        if action not in ["accept", "reject"]:
            return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)

        # Seul le leader de l'incident peut accepter/rejeter
        if collaboration.incident.taken_by != request.user:
            return Response(
                {"error": "Seul le leader de l'incident peut gérer les demandes de collaboration."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if action == "accept":
            collaboration.status = 'accepted'
            collaboration.save()
            return Response({"status": "Collaboration accepted"}, status=status.HTTP_200_OK)
        elif action == "reject":
            collaboration.status = 'declined'
            collaboration.save()
            return Response({"status": "Collaboration rejected"}, status=status.HTTP_200_OK)


class DeclineCollaborationView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        try:
            collaboration_id = request.data.get('collaboration_id')
            collaboration = Collaboration.objects.get(id=collaboration_id)

            # Seul le leader de l'incident peut décliner
            if collaboration.incident.taken_by != request.user:
                return Response(
                    {"error": "Seul le leader de l'incident peut décliner une collaboration."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            requesting_user = collaboration.user
            
            collaboration.status = 'declined'
            collaboration.save()
            
            send_email.delay(
                subject='Demande de collaboration déclinée',
                template_name='emails/decline_email.html',  
                context={
                    'incident_id': collaboration.incident.id,
                    'organisation': requesting_user.organisation
                },
                to_email=requesting_user.email,
            )
            
            notification_message = f'Votre demande de collaboration sur l\'incident {collaboration.incident.id} a été déclinée.'
            notification = Notification.objects.create(
                user=requesting_user,
                message=notification_message,
                colaboration=collaboration
            )
            notification.delete()

            return Response({"message": "Collaboration déclinée et notification supprimée."}, status=status.HTTP_200_OK)
        
        except Collaboration.DoesNotExist:
            return Response({"error": "Collaboration non trouvée"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AcceptCollaborationView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        try:
            collaboration_id = request.data.get('collaboration_id')
            if not collaboration_id:
                return Response(
                    {"error": "collaboration_id is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            collaboration = Collaboration.objects.get(id=collaboration_id)
            
            # Seul le leader de l'incident peut accepter
            if request.user != collaboration.incident.taken_by:
                return Response(
                    {"error": "Seul le leader de l'incident peut accepter une collaboration."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check if already accepted
            if collaboration.status == 'accepted':
                return Response(
                    {"error": "Cette collaboration a déjà été acceptée"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if expired
            if collaboration.end_date and collaboration.end_date <= timezone.now().date():
                return Response(
                    {"error": "Cette collaboration a expiré"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            collaboration.status = 'accepted'
            collaboration.save()
            
            return Response(
                {"message": "Collaboration acceptée avec succès"},
                status=status.HTTP_200_OK
            )
            
        except Collaboration.DoesNotExist:
            return Response(
                {"error": "Collaboration non trouvée"},
                status=status.HTTP_404_NOT_FOUND
            )
