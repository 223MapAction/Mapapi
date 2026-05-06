"""Collaboration endpoints (request, accept, decline, handle)."""
from django.db.models import Q
from django.utils import timezone

from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from ..models import Collaboration, Notification, COLLAB_ROLE_LEADER
from ..serializer import CollaborationSerializer
from ..Send_mails import send_email
from .common import CustomPageNumberPagination


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
