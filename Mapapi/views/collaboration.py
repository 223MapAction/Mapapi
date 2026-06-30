"""Collaboration endpoints (request, accept, decline, handle, dashboard)."""
from django.db.models import Q, Count
from django.utils import timezone

from rest_framework import status, generics, serializers
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse,
    OpenApiExample, inline_serializer,
)
from drf_spectacular.types import OpenApiTypes

from ..models import (
    Collaboration, Incident, Notification,
    COLLAB_ROLE_LEADER, COLLAB_ROLE_CONTRIBUTOR, COLLAB_ROLE_OBSERVER,
    COLLAB_STATUS_PENDING, COLLAB_STATUS_ACCEPTED,
)
from ..serializer import CollaborationSerializer, CollaborationEnrichedSerializer
from ..permissions import IsOrgAdmin, IsOrgOperative
from ..roles import is_super_admin, is_org_admin, is_bureau_agent
from ..Send_mails import send_email
from .common import CustomPageNumberPagination


def collaboration_scope_q(user, scope):
    """Q de portée pour les listes de collaboration, calquée sur les onglets de l'UI.

    - ``self``     : MES propres collaborations — celles que J'AI faites, ou dont je
      suis le leader (``user=moi``). C'est l'onglet « Mes collaborations » : une seule
      carte par incident, avec MON rôle. Corrige le doublon où le leader d'un incident
      voyait AUSSI la collaboration (contributor/observer) d'une autre organisation et
      apparaissait à tort comme « contributeur ».
    - ``received`` : demandes REÇUES sur les incidents que JE dirige, faites par
      d'AUTRES (``incident.taken_by=moi`` et ``user≠moi``). C'est l'onglet « Demandes ».
    - ``all`` (défaut) : union des deux — comportement historique, rétro-compatible.

    Le Super Admin supervise la plateforme : il voit TOUTES les collaborations,
    quel que soit le ``scope`` demandé (les filtres status/role/incident_id
    s'appliquent toujours par-dessus dans la vue).
    """
    if is_super_admin(user):
        return Q()
    scope = (scope or 'all').lower()
    if scope == 'self':
        return Q(user=user)
    if scope == 'received':
        return Q(incident__taken_by=user) & ~Q(user=user)
    return Q(user=user) | Q(incident__taken_by=user)


def collaboration_read_visibility_q(user):
    """Collaborations qu'un utilisateur a le droit de CONSULTER (détail en lecture).

    - Super Admin : toutes (supervision plateforme).
    - Admin d'org / agent de bureau : celles de SON organisation — créées par un
      membre de son org (``user`` ∈ org) OU portant sur un incident dont le leader
      est de son org (``incident.taken_by`` ∈ org) — en plus des siennes. C'est ce
      qui permet à un agent de bureau d'ouvrir le détail d'une collaboration de son
      org (ex. un incident interne pris en charge par son organisation) sans 404.
    - Autres rôles : uniquement les siennes (créées) + reçues (leader de l'incident).

    NB : réservé à la LECTURE. L'écriture (PATCH/DELETE) reste limitée au
    propriétaire / leader / super admin (cf. ``CollaborationDetailView``).
    """
    if is_super_admin(user):
        return Q()
    visible = Q(user=user) | Q(incident__taken_by=user)
    org_id = getattr(user, 'organisation_member_id', None)
    if org_id and (is_org_admin(user) or is_bureau_agent(user)):
        visible |= (
            Q(user__organisation_member_id=org_id)
            | Q(incident__taken_by__organisation_member_id=org_id)
        )
    return visible


@extend_schema_view(
    get=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_dashboard',
        summary="Dashboard des collaborations",
        description=(
            "Liste enrichie des collaborations de l'utilisateur authentifié "
            "(celles qu'il a demandées ou qu'il reçoit en tant que leader "
            "d'incident). Filtrable par statut applicatif, période et recherche."
        ),
        parameters=[
            OpenApiParameter(
                'scope', OpenApiTypes.STR, OpenApiParameter.QUERY,
                description=(
                    "Portée (onglets UI). 'self' = mes propres collaborations "
                    "(« Mes collaborations », 1 carte/incident avec MON rôle) ; "
                    "'received' = demandes reçues sur mes incidents (« Demandes ») ; "
                    "'all' (défaut) = les deux."
                ),
                enum=['self', 'received', 'all'],
            ),
            OpenApiParameter(
                'status', OpenApiTypes.STR, OpenApiParameter.QUERY,
                description="Filtre par statut applicatif (défaut 'all').",
                enum=['all', 'in-progress', 'completed', 'pending', 'accepted', 'declined'],
            ),
            OpenApiParameter(
                'date_from', OpenApiTypes.DATE, OpenApiParameter.QUERY,
                description="Borne basse : end_date >= date_from (ou end_date nulle).",
            ),
            OpenApiParameter(
                'date_to', OpenApiTypes.DATE, OpenApiParameter.QUERY,
                description="Borne haute : created_at <= date_to.",
            ),
            OpenApiParameter(
                'search', OpenApiTypes.STR, OpenApiParameter.QUERY,
                description="Recherche texte (titre incident, organisation, rôle, zone).",
            ),
        ],
        responses={200: CollaborationEnrichedSerializer(many=True)},
    ),
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
    # Paginé comme /collaboration/ : réponse {count, next, previous, results}
    # (cohérence des formats côté frontend).
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        user = self.request.user
        # ?scope=self | received | all (défaut). « Mes collaborations » -> self
        # (1 carte/incident avec MON rôle, plus de doublon côté leader) ;
        # « Demandes » -> received. cf. collaboration_scope_q.
        qs = Collaboration.objects.filter(
            collaboration_scope_q(user, self.request.query_params.get('scope'))
        ).select_related(
            'incident', 'user', 'user__organisation_member',
            'incident__taken_by', 'incident__taken_by__organisation_member',
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


@extend_schema_view(
    get=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_list',
        summary="Lister mes collaborations",
        description=(
            "Liste paginée des collaborations de l'utilisateur authentifié "
            "(celles qu'il a demandées ou qu'il reçoit en tant que leader). "
            "Filtrable par statut, rôle et incident."
        ),
        parameters=[
            OpenApiParameter(
                'status', OpenApiTypes.STR, OpenApiParameter.QUERY,
                description="Filtre par statut.", enum=['pending', 'accepted', 'declined'],
            ),
            OpenApiParameter(
                'role', OpenApiTypes.STR, OpenApiParameter.QUERY,
                description="Filtre par rôle.", enum=['leader', 'contributor', 'observer'],
            ),
            OpenApiParameter(
                'incident_id', OpenApiTypes.UUID, OpenApiParameter.QUERY,
                description="Filtre par incident (UUID).",
            ),
        ],
        responses={200: CollaborationSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_create',
        summary="Demander une collaboration",
        description=(
            "Demande à rejoindre un incident. Réservé aux admins d'organisation "
            "(IsOrgAdmin). Le rôle 'leader' est refusé (il est attribué "
            "automatiquement lors de la prise en charge). Le statut initial "
            "(pending/accepted) est calculé selon le mode de prise en charge de "
            "l'incident et le rôle demandé."
        ),
        request=CollaborationSerializer,
        responses={
            201: CollaborationSerializer,
            400: OpenApiResponse(
                description="Données invalides, rôle 'leader' demandé, ou "
                            "collaboration déjà existante sur cet incident.",
            ),
            403: OpenApiResponse(description="Réservé aux admins d'organisation."),
        },
        examples=[OpenApiExample(
            'Demande contributor',
            value={
                'incident': '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                'role': 'contributor',
                'motivation': 'Notre organisation peut intervenir sur cette zone.',
                'end_date': '2026-12-31',
            },
            request_only=True,
        )],
    ),
)
class CollaborationView(generics.CreateAPIView, generics.ListAPIView):
    """
    GET  /collaboration/  — liste paginée des collaborations de l'utilisateur
    POST /collaboration/  — demander à rejoindre un incident (role=contributor|observer, status=pending)
    """
    permission_classes = [IsAuthenticated]
    queryset = Collaboration.objects.all()
    serializer_class = CollaborationSerializer
    pagination_class = CustomPageNumberPagination

    def get_permissions(self):
        # « Demander une collaboration » (contributor/observer) = membres opérationnels
        # d'une organisation : Admin d'organisation OU agent de bureau. Le rôle 'leader'
        # reste refusé au niveau du serializer (prise en charge auto uniquement), donc un
        # agent de bureau ne peut jamais prendre l'incident en charge via cet endpoint.
        # La lecture (GET) reste ouverte à tout utilisateur authentifié.
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsOrgOperative()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        # ?scope=self | received | all (défaut). « Mes collaborations » -> self ;
        # « Demandes » -> received. cf. collaboration_scope_q.
        qs = Collaboration.objects.filter(
            collaboration_scope_q(user, self.request.query_params.get('scope'))
        ).select_related(
            'incident', 'user', 'user__organisation_member',
            'incident__taken_by', 'incident__taken_by__organisation_member',
        ).order_by('-id')

        # --- Filtres optionnels ---
        status_param = self.request.query_params.get('status')
        if status_param in ('pending', 'accepted', 'declined'):
            qs = qs.filter(status=status_param)

        role_param = self.request.query_params.get('role')
        if role_param in ('leader', 'contributor', 'observer'):
            qs = qs.filter(role=role_param)

        incident_id = self.request.query_params.get('incident_id')
        if incident_id:
            qs = qs.filter(incident_id=incident_id)

        return qs

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        incident = serializer.validated_data.get('incident')
        role = serializer.validated_data.get('role')

        # Empêcher doublon — uniquement si une collaboration ACTIVE existe déjà
        # (pending/accepted). Une demande précédemment REFUSÉE (declined/refused) ou
        # TERMINÉE peut être relancée : on supprime l'ancienne ligne (contrainte unique
        # incident+user) pour en recréer une et re-notifier le leader.
        existing = Collaboration.objects.filter(incident=incident, user=request.user).first()
        if existing and existing.status in (COLLAB_STATUS_PENDING, COLLAB_STATUS_ACCEPTED):
            return Response(
                {"error": "Vous avez déjà une collaboration active sur cet incident."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if existing:
            existing.delete()

        # --- Détermination du statut initial ---
        # Observer : toujours auto-accepté (toute org a le droit d'observer)
        # Contributor : auto-accepté si pas de leader désigné, sinon pending
        # En mode 'internal' : la collab arrive en pending (le propriétaire décide,
        #   et l'acceptation fait basculer l'incident en mode collaborative)
        if incident.take_in_charge_mode == 'internal':
            collab_status = 'pending'
        elif role == COLLAB_ROLE_OBSERVER:
            collab_status = 'accepted'
        elif role == COLLAB_ROLE_CONTRIBUTOR:
            collab_status = 'accepted' if incident.taken_by is None else 'pending'
        else:
            collab_status = 'pending'

        collaboration = serializer.save(user=request.user, status=collab_status)

        # Si pas encore de mode (incident jamais pris en charge), passer en collaborative
        if incident.take_in_charge_mode is None and collab_status == 'accepted':
            incident.take_in_charge_mode = 'collaborative'
            incident.save(update_fields=['take_in_charge_mode'])

        return Response(
            CollaborationSerializer(collaboration).data,
            status=status.HTTP_201_CREATED,
        )


_COLLAB_PK_PARAM = OpenApiParameter(
    'pk', OpenApiTypes.UUID, OpenApiParameter.PATH,
    description="ID de la collaboration (UUID).",
)


@extend_schema_view(
    get=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_retrieve',
        summary="Détail d'une collaboration",
        description=(
            "Détail d'une collaboration. Accessible au collaborateur lui-même, "
            "au leader de l'incident, ou à un super admin."
        ),
        parameters=[_COLLAB_PK_PARAM],
        responses={
            200: CollaborationSerializer,
            404: OpenApiResponse(description="Collaboration introuvable."),
        },
    ),
    put=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_update',
        summary="Remplacer une collaboration",
        description=(
            "Mise à jour complète d'une collaboration (collaborateur, leader de "
            "l'incident, ou super admin). Le statut reste piloté via les "
            "endpoints accept/decline."
        ),
        parameters=[_COLLAB_PK_PARAM],
        request=CollaborationSerializer,
        responses={
            200: CollaborationSerializer,
            400: OpenApiResponse(description="Données invalides."),
            404: OpenApiResponse(description="Collaboration introuvable."),
        },
    ),
    patch=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_partial_update',
        summary="Modifier une collaboration",
        description=(
            "Mise à jour partielle d'une collaboration (collaborateur, leader de "
            "l'incident, ou super admin)."
        ),
        parameters=[_COLLAB_PK_PARAM],
        request=CollaborationSerializer,
        responses={
            200: CollaborationSerializer,
            400: OpenApiResponse(description="Données invalides."),
            404: OpenApiResponse(description="Collaboration introuvable."),
        },
    ),
    delete=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_destroy',
        summary="Supprimer une collaboration",
        description=(
            "Supprime une collaboration (collaborateur, leader de l'incident, "
            "ou super admin)."
        ),
        parameters=[_COLLAB_PK_PARAM],
        responses={
            204: OpenApiResponse(description="Collaboration supprimée."),
            404: OpenApiResponse(description="Collaboration introuvable."),
        },
    ),
)
class CollaborationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /collaboration/<int:pk>/."""
    permission_classes = [IsAuthenticated]
    serializer_class = CollaborationSerializer
    queryset = Collaboration.objects.all()

    def get_queryset(self):
        user = self.request.user
        # LECTURE (GET) : un membre d'org (admin/agent de bureau) peut consulter le
        # détail d'une collaboration de SON organisation — pas seulement les siennes.
        if self.request.method in SAFE_METHODS:
            return Collaboration.objects.filter(collaboration_read_visibility_q(user))
        # ÉCRITURE (PATCH/DELETE) : réservée au propriétaire, au leader de l'incident,
        # ou au super admin — un agent de bureau ne modifie pas la collab d'un autre.
        if user.is_staff or user.is_superuser:
            return Collaboration.objects.all()
        return Collaboration.objects.filter(
            Q(user=user) | Q(incident__taken_by=user)
        )


class BulkCollaborationRequestView(APIView):
    # Spec §6 : « Demander une collaboration » = Admin d'organisation uniquement.
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    @extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_bulk_request',
        summary="Demandes de collaboration en lot",
        description=(
            "Crée plusieurs demandes de collaboration en une seule requête. "
            "Réservé aux admins d'organisation. Chaque élément est validé "
            "indépendamment ; renvoie 201 si toutes réussissent, 207 si "
            "certaines échouent (avec le détail par élément)."
        ),
        request=inline_serializer(
            name='BulkCollaborationRequest',
            fields={
                'requests': serializers.ListField(
                    child=inline_serializer(
                        name='BulkCollaborationRequestItem',
                        fields={
                            'incident_id': serializers.UUIDField(),
                            'role': serializers.ChoiceField(
                                choices=['contributor', 'observer'], required=False,
                            ),
                            'motivation': serializers.CharField(required=False),
                            'end_date': serializers.DateField(required=False),
                        },
                    ),
                ),
            },
        ),
        responses={
            201: OpenApiResponse(
                description="Toutes les demandes créées — {created, errors, message}.",
            ),
            207: OpenApiResponse(
                description="Statut mixte, certaines demandes ont échoué — "
                            "{created, errors, message}.",
            ),
            400: OpenApiResponse(description="'requests' doit être une liste non vide."),
            403: OpenApiResponse(description="Réservé aux admins d'organisation."),
        },
        examples=[OpenApiExample(
            'Lot de 2 demandes',
            value={'requests': [
                {
                    'incident_id': '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                    'role': 'contributor',
                    'motivation': 'Appui terrain disponible.',
                    'end_date': '2026-12-31',
                },
                {'incident_id': '5fa85f64-5717-4562-b3fc-2c963f66afa6', 'role': 'observer'},
            ]},
            request_only=True,
        )],
    )
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
    # Spec §6 : accepter/refuser une collaboration (côté leader) = Admin d'organisation.
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    @extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_handle_request',
        summary="Accepter/rejeter une demande (leader)",
        description=(
            "Le leader de l'incident accepte ou rejette une demande de "
            "collaboration. Réservé aux admins d'organisation et au leader de "
            "l'incident. Accepter une collab fait basculer un incident en mode "
            "'internal' vers 'collaborative'."
        ),
        parameters=[
            OpenApiParameter(
                'collaboration_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                description="ID de la collaboration (UUID).",
            ),
            OpenApiParameter(
                'action', OpenApiTypes.STR, OpenApiParameter.PATH,
                description="Action à effectuer.", enum=['accept', 'reject'],
            ),
        ],
        request=None,
        responses={
            200: OpenApiResponse(
                description="{status: 'Collaboration accepted' | 'Collaboration rejected'}.",
            ),
            400: OpenApiResponse(description="Action invalide (différente de accept/reject)."),
            403: OpenApiResponse(
                description="Seul le leader de l'incident peut gérer la demande.",
            ),
            404: OpenApiResponse(description="Collaboration introuvable."),
        },
    )
    def post(self, request, collaboration_id, action, format=None):
        try:
            collaboration = Collaboration.objects.get(id=collaboration_id)
        except Collaboration.DoesNotExist:
            return Response({"error": "Collaboration not found"}, status=status.HTTP_404_NOT_FOUND)

        if action not in ["accept", "reject"]:
            return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)

        # Seul le leader de l'incident peut accepter/rejeter
        is_leader = (
            collaboration.incident.taken_by == request.user or
            Collaboration.objects.filter(
                incident=collaboration.incident,
                user=request.user,
                role='leader',
                status='accepted'
            ).exists()
        )
        if not is_leader:
            return Response(
                {"error": "Seul le leader de l'incident peut gérer les demandes de collaboration."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if action == "accept":
            collaboration.status = 'accepted'
            collaboration.save()
            # Si l'incident était en mode internal, accepter une collab externe
            # le fait basculer en mode collaborative
            incident = collaboration.incident
            if incident.take_in_charge_mode == 'internal':
                incident.take_in_charge_mode = 'collaborative'
                incident.save(update_fields=['take_in_charge_mode'])
            return Response({"status": "Collaboration accepted"}, status=status.HTTP_200_OK)
        elif action == "reject":
            collaboration.status = 'declined'
            collaboration.save()
            return Response({"status": "Collaboration rejected"}, status=status.HTTP_200_OK)


class DeclineCollaborationView(APIView):
    # Spec §6 : décliner une collaboration (côté leader) = Admin d'organisation.
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    @extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_decline',
        summary="Décliner une collaboration (leader)",
        description=(
            "Le leader de l'incident décline une demande de collaboration "
            "identifiée par {collaboration_id} dans le corps. Réservé aux admins "
            "d'organisation et au leader. Envoie un email au demandeur."
        ),
        request=inline_serializer(
            name='DeclineCollaborationRequest',
            fields={'collaboration_id': serializers.UUIDField()},
        ),
        responses={
            200: OpenApiResponse(description="{message} — collaboration déclinée."),
            403: OpenApiResponse(description="Seul le leader de l'incident peut décliner."),
            404: OpenApiResponse(description="Collaboration introuvable."),
            500: OpenApiResponse(description="Erreur serveur inattendue."),
        },
    )
    def post(self, request, *args, **kwargs):
        try:
            collaboration_id = request.data.get('collaboration_id')
            collaboration = Collaboration.objects.get(id=collaboration_id)

            # Seul le leader de l'incident peut décliner
            is_leader = (
                collaboration.incident.taken_by == request.user or
                Collaboration.objects.filter(
                    incident=collaboration.incident,
                    user=request.user,
                    role='leader',
                    status='accepted'
                ).exists()
            )
            if not is_leader:
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
            
            notification_message = f"Votre demande de collaboration sur l'incident « {collaboration.incident.title} » a été déclinée."
            notification = Notification.objects.create(
                user=requesting_user,
                notif_type='collaboration_declined',
                message=notification_message,
                colaboration=collaboration,
                incident=collaboration.incident,
            )
            notification.delete()

            return Response({"message": "Collaboration déclinée et notification supprimée."}, status=status.HTTP_200_OK)
        
        except Collaboration.DoesNotExist:
            return Response({"error": "Collaboration non trouvée"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AcceptCollaborationView(APIView):
    # Spec §6 : accepter une collaboration (côté leader) = Admin d'organisation.
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    @extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='collaborations_accept',
        summary="Accepter une collaboration (leader)",
        description=(
            "Le leader de l'incident accepte une demande identifiée par "
            "{collaboration_id} dans le corps. Réservé aux admins d'organisation "
            "et au leader. Bascule éventuelle de l'incident 'internal' vers "
            "'collaborative'. Monté sur deux routes : /accept-collaboration/ et "
            "/collaborations/accept/."
        ),
        request=inline_serializer(
            name='AcceptCollaborationRequest',
            fields={'collaboration_id': serializers.UUIDField()},
        ),
        responses={
            200: OpenApiResponse(description="{message} — collaboration acceptée."),
            400: OpenApiResponse(
                description="collaboration_id manquant, déjà acceptée, ou expirée.",
            ),
            403: OpenApiResponse(description="Seul le leader de l'incident peut accepter."),
            404: OpenApiResponse(description="Collaboration introuvable."),
        },
    )
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
            is_leader = (
                collaboration.incident.taken_by == request.user or
                Collaboration.objects.filter(
                    incident=collaboration.incident,
                    user=request.user,
                    role='leader',
                    status='accepted'
                ).exists()
            )
            if not is_leader:
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

            # Bascule éventuelle internal → collaborative
            incident = collaboration.incident
            if incident.take_in_charge_mode == 'internal':
                incident.take_in_charge_mode = 'collaborative'
                incident.save(update_fields=['take_in_charge_mode'])

            return Response(
                {"message": "Collaboration acceptée avec succès"},
                status=status.HTTP_200_OK
            )
            
        except Collaboration.DoesNotExist:
            return Response(
                {"error": "Collaboration non trouvée"},
                status=status.HTTP_404_NOT_FOUND
            )
