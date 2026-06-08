"""Message & response message endpoints + collaboration discussion messages."""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from rest_framework import status, generics
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from ..serializer import *
from ..models import Collaboration, Incident, COLLAB_ROLE_LEADER
from .common import CustomPageNumberPagination


@extend_schema(
    description="Endpoint allowing retrival, updating and deletion of Message.",
    responses={200: MessageSerializer, 404: "message not found"},  
)
class MessageAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Message.objects.all()
    serializer_class = MessageSerializer

    def get(self, request, id, format=None):
        try:
            item = Message.objects.get(pk=id)
            serializer = MessageGetSerializer(item)
            return Response(serializer.data)
        except Message.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = Message.objects.get(pk=id)
        except Message.DoesNotExist:
            return Response(status=404)
        serializer = MessageSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = Message.objects.get(pk=id)
        except Message.DoesNotExist:
            return Response(status=404)
        item.delete()
        return Response(status=204)

@extend_schema(
    description="Endpoint allowing retrieval and creating of message.",
    responses={201: MessageSerializer, 400: "serializer error"},  
)
class MessageAPIListView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    
    def get(self, request, format=None):
        items = Message.objects.order_by('pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = MessageGetSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        serializer = MessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()

            if 'user_id' in request.data and request.data['user_id']:
                elu = User.objects.get(pk=request.data['user_id'])
                subject, from_email, to = '[MAP ACTION] - Nouveau Message', settings.EMAIL_HOST_USER, elu.email
                html_content = render_to_string('mail_message_elu.html', {'prenom': elu.first_name,
                                                                          'nom': elu.last_name})  # render with dynamic value#
                text_content = strip_tags(html_content)  # Strip the html tag. So people can see the pure text at least.
                msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
                msg.attach_alternative(html_content, "text/html")
                msg.send()

            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

@extend_schema(
    description="Endpoint allowing retrivial of message by community.",
    responses={200: MessageSerializer, 404: "message not found"},  
)
class MessageByComAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Message.objects.all()
    serializer_class = MessageSerializer

    def get(self, request, id, format=None, **kwargs):
        try:
            item = Message.objects.filter(communaute=id)
            serializer = MessageSerializer(item, many=True)
            return Response(serializer.data)
        except Message.DoesNotExist:
            return Response(status=404)

@extend_schema(
    description="Endpoint allowing retrivial of message by zone.",
    responses={200: MessageSerializer, 404: "message not found"},  
)
class MessageByZoneAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Message.objects.all()
    serializer_class = MessageSerializer

    def get(self, request, format=None, **kwargs):
        try:
            zone = kwargs['zone']
            item = Message.objects.filter(zone__name=zone)
            serializer = MessageByZoneSerializer(item, many=True)
            return Response(serializer.data)
        except Message.DoesNotExist:
            return Response(status=404)


@extend_schema(
    description="Endpoint for managing response messages.",
    request=ResponseMessageSerializer,
    responses={201: ResponseMessageSerializer, 400: "Bad Request"},
)
class ResponseMessageAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = ResponseMessage.objects.all()
    serializer_class = ResponseMessageSerializer

    def get(self, request, id, format=None):
        try:
            item = ResponseMessage.objects.get(pk=id)
            serializer = ResponseMessageSerializer(item)
            return Response(serializer.data)
        except ResponseMessage.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = ResponseMessage.objects.get(pk=id)
        except ResponseMessage.DoesNotExist:
            return Response(status=404)
        serializer = ResponseMessageSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = ResponseMessage.objects.get(pk=id)
        except ResponseMessage.DoesNotExist:
            return Response(status=404)
        item.delete()
        return Response(status=204)

@extend_schema(
    description="Endpoint for managing response messages.",
    request=ResponseMessageSerializer,
    responses={201: ResponseMessageSerializer, 400: "Bad Request"},
)
class ResponseMessageAPIListView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = ResponseMessage.objects.all()
    serializer_class = ResponseMessageSerializer

    def get(self, request, format=None):
        items = ResponseMessage.objects.order_by('pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = ResponseMessageSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        serializer = ResponseMessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

@extend_schema(
    description="Endpoint for retrieving responses by message ID.",
    responses={200: ResponseMessageSerializer(many=True), 404: "Not Found"},
)
class ResponseByMessageAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = ResponseMessage.objects.all()
    serializer_class = ResponseMessageSerializer

    def get(self, request, id, format=None):
        try:
            item = ResponseMessage.objects.filter(message=id)
            serializer = ResponseMessageSerializer(item, many=True)
            return Response(serializer.data)
        except ResponseMessage.DoesNotExist:
            return Response(status=404)

@extend_schema(
    description="Endpoint for retrieving messages by user ID.",
    responses={200: MessageGetSerializer(many=True), 404: "Not Found"},
)
class MessageByUserAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Message.objects.all()
    serializer_class = MessageSerializer

    def get(self, request, id, format=None):
        try:
            item = Message.objects.filter(user_id=id)
            serializer = MessageGetSerializer(item, many=True)
            return Response(serializer.data)
        except Message.DoesNotExist:
            return Response(status=404)


class DiscussionMessageView(generics.ListCreateAPIView):
    """
    Espace de discussion (chat de groupe) d'un incident.

    Tous les collaborateurs acceptés + le leader voient tous les messages
    de l'incident. Accepte texte, audio et pièces jointes (PDF, Excel, Word).
    """
    serializer_class = DiscussionMessageSerializer
    permission_classes = [IsAuthenticated]

    def _get_user_collaboration(self, incident_id, user):
        """Retourne la Collaboration acceptée de l'utilisateur sur cet incident.

        Tous les rôles (leader, contributor, observer) avec status='accepted'
        peuvent participer à la discussion. Le leader désigné via
        incident.taken_by sans entrée Collaboration est aussi autorisé : on
        crée alors automatiquement sa Collaboration avec role='leader'.

        En mode 'internal' : seuls les membres de l'organisation propriétaire
        (celle de incident.taken_by) peuvent participer.

        Lève NotFound si l'utilisateur n'est pas collaborateur accepté.
        """
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            raise NotFound("Incident introuvable.")

        # --- Mode INTERNAL : restreint aux membres de l'org propriétaire ---
        if incident.take_in_charge_mode == 'internal':
            owner = incident.taken_by
            if not owner or not owner.organisation_member_id:
                raise NotFound("Discussion indisponible pour cet incident.")
            if user.organisation_member_id != owner.organisation_member_id:
                raise NotFound("Cet incident est en mode interne, réservé à l'organisation qui l'a pris en charge.")
            # Auto-crée une collaboration leader/accepted pour les membres de l'org propriétaire
            collab, _ = Collaboration.objects.get_or_create(
                incident=incident,
                user=user,
                defaults={'role': COLLAB_ROLE_LEADER, 'status': 'accepted'},
            )
            if collab.status != 'accepted':
                collab.status = 'accepted'
                collab.save(update_fields=['status'])
            return collab

        # 1) Tente de récupérer la Collaboration existante (tous rôles confondus)
        collab = Collaboration.objects.filter(
            incident__id=incident_id,
            user=user,
            status='accepted',
        ).first()
        if collab:
            return collab

        # 2) Cas du leader désigné via incident.taken_by sans entrée Collaboration
        if incident.taken_by_id == user.id:
            # Auto-création de la Collaboration leader pour permettre la discussion
            collab, _ = Collaboration.objects.get_or_create(
                incident=incident,
                user=user,
                defaults={
                    'role': COLLAB_ROLE_LEADER,
                    'status': 'accepted',
                },
            )
            if collab.status != 'accepted':
                collab.status = 'accepted'
                collab.save(update_fields=['status'])
            return collab

        raise NotFound("Vous ne participez pas à la discussion de cet incident.")

    def get_queryset(self):
        incident_id = self.kwargs.get('incident_id')
        user = self.request.user

        # Vérifier que l'utilisateur est collaborateur accepté
        self._get_user_collaboration(incident_id, user)

        # Chat de groupe : tous les messages de l'incident
        return DiscussionMessage.objects.filter(
            incident__id=incident_id
        ).order_by('created_at')
    
    def perform_create(self, serializer):
        incident_id = self.kwargs.get('incident_id')
        user = self.request.user

        collaboration = self._get_user_collaboration(incident_id, user)
        incident = collaboration.incident

        if incident.etat == "resolved":
            raise ValidationError("Cet incident est résolu, la discussion est terminée.")

        # recipient est optionnel dans un chat de groupe
        # mais on le garde pour la rétro-compatibilité
        recipient_id = self.request.data.get('recipient')
        recipient = None
        if recipient_id:
            try:
                recipient = User.objects.get(pk=recipient_id)
            except User.DoesNotExist:
                pass

        serializer.save(
            sender=user,
            incident=incident,
            collaboration=collaboration,
            recipient=recipient,
        )
