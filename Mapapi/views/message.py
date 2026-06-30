"""Message & response message endpoints + collaboration discussion messages."""
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from rest_framework import status, generics
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiExample,
)
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from ..models import Collaboration, Incident, COLLAB_ROLE_LEADER
from .common import CustomPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='messages_retrieve',
        summary="Détail d'un message",
        description="Retourne un message (objet, contenu, zone, communauté, élu destinataire) par son identifiant. Endpoint public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant UUID du message.")],
        responses={200: MessageGetSerializer, 404: OpenApiResponse(description="Message introuvable.")},
    ),
    put=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='messages_update',
        summary="Modifier un message",
        description="Met à jour un message existant. Endpoint public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant UUID du message.")],
        request=MessageSerializer,
        responses={
            200: MessageSerializer,
            400: OpenApiResponse(description="Données invalides."),
            404: OpenApiResponse(description="Message introuvable."),
        },
    ),
    delete=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='messages_destroy',
        summary="Supprimer un message",
        description="Supprime définitivement un message. Endpoint public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant UUID du message.")],
        responses={
            204: OpenApiResponse(description="Message supprimé."),
            404: OpenApiResponse(description="Message introuvable."),
        },
    ),
    post=extend_schema(exclude=True),
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

@extend_schema_view(
    get=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='messages_list',
        summary="Lister les messages",
        description="Retourne la liste paginée de tous les messages (questions adressées aux élus), triés par identifiant. Endpoint public.",
        responses={200: MessageGetSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='messages_create',
        summary="Créer un message",
        description="Crée un nouveau message. Si `user_id` (élu destinataire) est fourni, un e-mail de notification lui est envoyé. Endpoint public.",
        request=MessageSerializer,
        responses={
            201: MessageSerializer,
            400: OpenApiResponse(description="Données invalides."),
        },
        examples=[
            OpenApiExample(
                'Message à un élu',
                value={
                    'objet': 'Problème de salubrité',
                    'message': "Les déchets ne sont pas ramassés depuis deux semaines.",
                    'zone': '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                    'communaute': '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                    'user_id': '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                },
                request_only=True,
            ),
        ],
    ),
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

@extend_schema_view(
    get=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='messages_by_communaute',
        summary="Messages d'une communauté",
        description="Retourne les messages rattachés à une communauté. Endpoint public. Note : cette route partage le chemin `/message/` et est masquée à l'exécution par la liste des messages.",
        responses={
            200: MessageSerializer(many=True),
            404: OpenApiResponse(description="Aucun message."),
        },
    ),
    post=extend_schema(exclude=True),
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

@extend_schema_view(
    get=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='messages_by_zone',
        summary="Messages par zone",
        description="Retourne les messages d'une zone, filtrés par le nom de la zone (`zone__name`). Endpoint public.",
        parameters=[OpenApiParameter('zone', OpenApiTypes.STR, OpenApiParameter.PATH, description="Nom de la zone.")],
        responses={
            200: MessageByZoneSerializer(many=True),
            404: OpenApiResponse(description="Aucun message."),
        },
    ),
    post=extend_schema(exclude=True),
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


@extend_schema_view(
    get=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='response_msg_retrieve',
        summary="Détail d'une réponse",
        description="Retourne une réponse à un message (réponse d'un élu) par son identifiant. Endpoint public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant UUID de la réponse.")],
        responses={200: ResponseMessageSerializer, 404: OpenApiResponse(description="Réponse introuvable.")},
    ),
    put=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='response_msg_update',
        summary="Modifier une réponse",
        description="Met à jour une réponse existante. Endpoint public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant UUID de la réponse.")],
        request=ResponseMessageSerializer,
        responses={
            200: ResponseMessageSerializer,
            400: OpenApiResponse(description="Données invalides."),
            404: OpenApiResponse(description="Réponse introuvable."),
        },
    ),
    delete=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='response_msg_destroy',
        summary="Supprimer une réponse",
        description="Supprime définitivement une réponse. Endpoint public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant UUID de la réponse.")],
        responses={
            204: OpenApiResponse(description="Réponse supprimée."),
            404: OpenApiResponse(description="Réponse introuvable."),
        },
    ),
    post=extend_schema(exclude=True),
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

@extend_schema_view(
    get=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='response_msg_list',
        summary="Lister les réponses",
        description="Retourne la liste paginée de toutes les réponses aux messages, triées par identifiant. Endpoint public.",
        responses={200: ResponseMessageSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='response_msg_create',
        summary="Créer une réponse",
        description="Crée une réponse à un message. Endpoint public.",
        request=ResponseMessageSerializer,
        responses={
            201: ResponseMessageSerializer,
            400: OpenApiResponse(description="Données invalides."),
        },
    ),
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

@extend_schema_view(
    get=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='messages_by_user',
        summary="Messages d'un élu",
        description="Retourne les messages adressés à un utilisateur (élu) donné. Endpoint public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant UUID de l'utilisateur (élu).")],
        responses={
            200: MessageGetSerializer(many=True),
            404: OpenApiResponse(description="Aucun message."),
        },
    ),
    post=extend_schema(exclude=True),
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


@extend_schema_view(
    get=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='messages_discussion_list',
        summary="Discussion d'un incident",
        description=(
            "Messages du chat de groupe d'un incident, triés par date. Réservé aux "
            "collaborateurs acceptés (et au leader) ; en mode interne, réservé aux "
            "membres de l'organisation propriétaire.\n\n"
            "Pagination curseur (chargement progressif) : sans `limit`, renvoie tous "
            "les messages (tableau, ordre chronologique). Avec `limit`, renvoie un "
            "objet `{messages, has_more, next_before}` avec les N messages les plus "
            "récents (ordre chronologique). Pour charger les plus anciens (scroll vers "
            "le haut), rappeler avec `?before=<id du plus ancien message déjà chargé>`."
        ),
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant UUID de l'incident."),
            OpenApiParameter('limit', OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Nombre de messages les plus récents à renvoyer (1–100). Absent = tous."),
            OpenApiParameter('before', OpenApiTypes.UUID, OpenApiParameter.QUERY,
                             description="Curseur : messages ANTÉRIEURS à ce message (son id). À utiliser avec `limit`."),
        ],
        responses={
            200: DiscussionMessageSerializer(many=True),
            400: OpenApiResponse(description="limit invalide, ou 'before' invalide/introuvable."),
            401: OpenApiResponse(description="Authentification requise."),
            404: OpenApiResponse(description="Incident introuvable ou accès non autorisé."),
        },
    ),
    post=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='messages_discussion_create',
        summary="Envoyer un message de discussion",
        description="Publie un message dans le chat de groupe d'un incident (texte, audio et/ou pièce jointe en multipart). Réservé aux collaborateurs acceptés ; bloqué si l'incident est résolu. `recipient` est optionnel.",
        parameters=[OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant UUID de l'incident.")],
        request=DiscussionMessageSerializer,
        responses={
            201: DiscussionMessageSerializer,
            400: OpenApiResponse(description="Message vide ou incident résolu."),
            401: OpenApiResponse(description="Authentification requise."),
            404: OpenApiResponse(description="Incident introuvable ou accès non autorisé."),
        },
    ),
)
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

    def list(self, request, *args, **kwargs):
        # get_queryset() applique le contrôle d'accès (collaborateur accepté) et
        # renvoie les messages de l'incident triés par date croissante.
        base = self.get_queryset()

        # --- Pagination curseur (chargement progressif, identique au chat IA) ---
        # Sans `limit` : tous les messages (tableau, rétro-compatible).
        # Avec `limit` : les N messages les PLUS RÉCENTS (ordre chronologique croissant
        # pour l'affichage) + `has_more` + `next_before`. Pour charger les plus anciens
        # (scroll vers le haut), rappeler avec `?before=<id du plus ancien chargé>`.
        limit_param = request.query_params.get('limit')
        if limit_param is None:
            serializer = self.get_serializer(base, many=True)
            return Response(serializer.data)

        try:
            limit = int(limit_param)
        except (TypeError, ValueError):
            return Response({"detail": "limit doit être un entier."}, status=status.HTTP_400_BAD_REQUEST)
        limit = max(1, min(limit, 100))

        # Du plus récent au plus ancien (keyset sur created_at + id).
        qs = base.order_by('-created_at', '-id')

        before = request.query_params.get('before')
        if before:
            try:
                cursor = base.filter(pk=before).values('created_at', 'id').first()
            except (ValueError, DjangoValidationError):
                cursor = None
            if not cursor:
                return Response(
                    {"detail": "Paramètre 'before' invalide ou introuvable."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(
                Q(created_at__lt=cursor['created_at'])
                | Q(created_at=cursor['created_at'], id__lt=cursor['id'])
            )

        rows = list(qs[:limit + 1])
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_before = str(rows[-1].id) if (rows and has_more) else None
        rows.reverse()  # ordre chronologique croissant pour l'affichage
        serializer = self.get_serializer(rows, many=True)
        return Response({
            "messages": serializer.data,
            "has_more": has_more,
            "next_before": next_before,
        })

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
