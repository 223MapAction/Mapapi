"""Notification & user-action endpoints."""
from rest_framework import viewsets, generics, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view

from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination, NotificationPagination


@extend_schema_view(
    list=extend_schema(
        tags=['Notifications'],
        operation_id='notifications_list',
        summary='Mes notifications',
        description=(
            "Toutes les notifications de l'utilisateur connecté, **plus récentes "
            "d'abord**, paginées (20/page, `?page=&page_size=`). Chaque notification "
            "porte un champ `link` (cible de redirection au clic). Filtre `?read=true|false` "
            "(ex. `?read=false` pour les non lues → `count` = nombre de non lues). "
            "Authentification requise."
        ),
        parameters=[
            OpenApiParameter('read', OpenApiTypes.BOOL, OpenApiParameter.QUERY,
                             description="Filtre lues/non lues (true|false)."),
        ],
        responses={200: NotificationSerializer(many=True)},
    )
)
class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user).order_by('-created_at')
        read = self.request.query_params.get('read')
        if read is not None:
            qs = qs.filter(read=(str(read).lower() in ('1', 'true', 'yes')))
        return qs

    def list(self, request, *args, **kwargs):
        """Liste paginée + compteurs GLOBAUX lu/non-lu de l'utilisateur.

        `unread_count`, `read_count` et `total_count` sont calculés sur TOUTES les
        notifications de l'utilisateur (indépendamment du filtre `?read`), pour
        alimenter un badge sans second appel.
        """
        response = super().list(request, *args, **kwargs)
        base = Notification.objects.filter(user=request.user)
        unread = base.filter(read=False).count()
        read = base.filter(read=True).count()
        if isinstance(response.data, dict):
            response.data['unread_count'] = unread
            response.data['read_count'] = read
            response.data['total_count'] = unread + read
        return response

    @staticmethod
    def _as_bool(val, default=True):
        if isinstance(val, bool):
            return val
        if val is None:
            return default
        return str(val).lower() in ('1', 'true', 'yes')

    @extend_schema(
        tags=['Notifications'],
        operation_id='notifications_mark_read',
        summary='Marquer une notification comme lue',
        description="Met à jour le statut de lecture d'UNE notification (au clic). "
                    "Seul le champ `read` est modifiable (les autres sont ignorés) ; "
                    "défaut `read=true`. Limité aux notifications de l'utilisateur connecté.",
        request=None,
        responses={200: NotificationSerializer},
    )
    def partial_update(self, request, *args, **kwargs):
        """PATCH /notifications/<pk>/ — bascule `read` (true par défaut).

        ``get_object`` s'appuie sur ``get_queryset`` (filtré par utilisateur) :
        impossible de toucher la notification d'un autre (→ 404).
        """
        instance = self.get_object()
        instance.read = self._as_bool(request.data.get('read', True))
        instance.save(update_fields=['read'])
        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Notifications'],
        operation_id='notifications_mark_all_read',
        summary='Tout marquer comme lu',
        description="Marque TOUTES les notifications non lues de l'utilisateur connecté "
                    "comme lues. Renvoie le nombre de notifications mises à jour.",
        request=None,
        responses={200: OpenApiTypes.OBJECT},
    )
    def mark_all_read(self, request, *args, **kwargs):
        """POST /notifications/mark-all-read/ — marque toutes mes notifs comme lues."""
        updated = Notification.objects.filter(user=request.user, read=False).update(read=True)
        return Response({'marked_read': updated}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        tags=['Notifications'],
        operation_id='user_actions_list',
        summary='Mes actions (journal)',
        description="Journal des actions de l'utilisateur connecté. Authentification requise.",
        responses={200: UserActionSerializer(many=True)},
    )
)
class UserActionView(viewsets.ModelViewSet):
    queryset = UserAction.objects.all()
    serializer_class = UserActionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@extend_schema(
    tags=['Notifications'],
    operation_id='activity_feed',
    summary="Flux d'activité (autres organisations)",
    description="Activité récente de la plateforme **en dehors de l'organisation de "
                "l'utilisateur connecté** (prises en charge / résolutions d'incidents, "
                "etc.), plus récente d'abord, paginée (20/page). Chaque élément expose "
                "`action`, `user_name`, `organisation_name`, `created_at`. Auth requise.",
    responses={200: ActivityFeedSerializer(many=True)},
)
class ActivityFeedView(generics.ListAPIView):
    """GET /activity-feed/ — activité de la plateforme hors organisation connectée."""
    permission_classes = [IsAuthenticated]
    serializer_class = ActivityFeedSerializer
    pagination_class = NotificationPagination

    def get_queryset(self):
        qs = UserAction.objects.select_related('user', 'user__organisation_member')
        org_id = getattr(self.request.user, 'organisation_member_id', None)
        if org_id:
            qs = qs.exclude(user__organisation_member_id=org_id)
        return qs  # tri par défaut depuis Meta (-created_at, -timeStamp)

    def list(self, request, *args, **kwargs):
        """Liste paginée + compteurs total / vues / non-vues du flux.

        `unseen_count` = éléments du flux postérieurs à la dernière consultation
        (`user.activity_seen_at`) ; tout est « non vu » si l'utilisateur n'a jamais
        consulté le flux. `POST /activity-feed/mark-seen/` met l'horodatage à jour.
        """
        response = super().list(request, *args, **kwargs)
        if isinstance(response.data, dict):
            qs = self.get_queryset()
            total = qs.count()
            seen_at = getattr(request.user, 'activity_seen_at', None)
            unseen = qs.filter(created_at__gt=seen_at).count() if seen_at else total
            response.data['total_count'] = total
            response.data['unseen_count'] = unseen
            response.data['seen_count'] = total - unseen
        return response


@extend_schema(
    tags=['Notifications'],
    operation_id='activity_feed_mark_seen',
    summary="Marquer le flux d'activité comme vu",
    description="Met à jour la date de dernière consultation du flux d'activité "
                "de l'utilisateur connecté → `unseen_count` repasse à 0. Auth requise.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
class ActivityFeedMarkSeenView(APIView):
    """POST /activity-feed/mark-seen/ — marque le flux d'activité comme vu."""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        from django.utils import timezone
        request.user.activity_seen_at = timezone.now()
        request.user.save(update_fields=['activity_seen_at'])
        return Response({'activity_seen_at': request.user.activity_seen_at},
                        status=status.HTTP_200_OK)
