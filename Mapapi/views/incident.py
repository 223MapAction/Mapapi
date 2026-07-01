"""Incident endpoints: CRUD, filters, search, reporting windows (monthly/weekly), handling actions."""
import subprocess
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q, Prefetch, Count
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse,
    OpenApiExample, inline_serializer,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers as drf_serializers

from ..serializer import *
from ..models import (
    Collaboration, COLLAB_ROLE_LEADER, COLLAB_ROLE_CONTRIBUTOR, COLLAB_ROLE_OBSERVER,
    COLLAB_STATUS_ACCEPTED, COLLAB_STATUS_TERMINATED, COLLAB_STATUS_PENDING,
    RESOLVED, TASK_DONE, TASK_FAILED,
    DECLARED, TAKEN, RESOLUTION_PREPARED, IN_VALIDATION, RESOLVED_DEFINITIVE,
    ORG_ROLE_FIELD, ORG_ROLE_ADMIN, ORG_ROLE_BUREAU,
    Organisation, IncidentOrgAssignment,
    ORG_ASSIGNMENT_PENDING, ORG_ASSIGNMENT_ACCEPTED, ORG_ASSIGNMENT_DECLINED,
    Prediction, PredictionStatus, Notification,
    ChatHistory, CHAT_ROLE_USER, CHAT_ROLE_ASSISTANT,
    Rapport, IncidentAssignment,
)
from ..permissions import (
    IsIncidentLeader, IsSuperAdminOrOrgOwnIncident, IsSuperAdmin,
    IsOrgAdmin, IsAgentBureau, IsOrgOperative, IsSuperAdminRole,
)
from ..roles import is_org_admin
from ..tasks import analyze_incident_with_model_task
from ..Send_mails import send_email
import logging

logger = logging.getLogger(__name__)
from ..services.model_chat_client import ask_model_chat
from .common import CustomPageNumberPagination, IncidentPagination, FieldReportPagination, deaccent
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import check_password
from .. import roles as web_roles


def visible_incidents_qs(base_qs, user):
    """Incidents visibles dans les listes incident.

    Décision produit (2026-07) : TOUT utilisateur authentifié — super_admin,
    org_admin, agent de terrain, etc. — voit l'ENSEMBLE des incidents dans les
    listes (cohérent avec le total affiché sur le dashboard). Les appels NON
    authentifiés (endpoints publics) restent limités aux incidents publics pour
    ne pas exposer les incidents internes (is_public=False).
    """
    # Les incidents en corbeille (is_deleted) ne figurent jamais dans les listes
    # (cohérent avec le total du dashboard, qui exclut aussi la corbeille).
    base_qs = base_qs.filter(is_deleted=False)
    if user and getattr(user, 'is_authenticated', False):
        return base_qs
    return base_qs.filter(is_public=True)


# Correspondance code pays (front / `intervention_country`) -> noms géocodés
# possibles (`Prediction.country`), en formes NON accentuées : comparées via
# __unaccent__iexact (donc « Sénégal » ↔ « Senegal », « Guinée » ↔ « Guinee »/
# « Guinea »…). Couvre les variantes FR et EN du géocodage.
COUNTRY_GEOCODE_ALIASES = {
    'mali': ['Mali'],
    'senegal': ['Senegal'],
    'guinea': ['Guinee', 'Guinea'],
    'burkina_faso': ['Burkina Faso'],
    'niger': ['Niger'],
    'cote_divoire': ["Cote d'Ivoire", 'Ivory Coast'],
    'mauritania': ['Mauritanie', 'Mauritania'],
}


# États « résolus » exposés par /incidentResolved/ (résolu + résolu définitif).
# /incidentNotResolved/ = tout le reste (declared, taken_into_account, in_progress,
# in_validation) — et non plus seulement 'declared' comme avant.
RESOLVED_ETATS = [RESOLVED, RESOLVED_DEFINITIVE]


def org_own_work_q(user):
    """Q : incidents que MON organisation gère déjà — à EXCLURE des listes
    publiques résolus/non-résolus (ils sont déjà dans « Mes interventions »).

    Deux cas, exactement comme « Mes interventions » (OrgIncidentsView) :
      - pris en charge EN INTERNE par mon org (``take_in_charge_mode='internal'``
        ET ``taken_by`` ∈ mon org), OU
      - signalés par un agent de TERRAIN de mon org (``user_id`` ∈ mes agents).

    Utilisateur sans organisation → rien à exclure (Q qui ne matche aucune ligne).
    """
    org = getattr(user, 'organisation_member', None)
    if not org:
        return Q(pk__in=[])
    agent_ids = list(org.members.filter(org_role=ORG_ROLE_FIELD).values_list('id', flat=True))
    internal_q = Q(take_in_charge_mode__iexact='internal', taken_by__organisation_member=org)
    agents_q = Q(user_id__in=agent_ids)
    return internal_q | agents_q


def engage_incident(incident, leader):
    """Engage l'organisation sur l'incident (sémantique « prise en compte »).

    Reprend la logique de TakeInChargeView (mode interne) : si l'incident est
    'declared', il passe en 'taken_into_account', avec taken_by = `leader` et
    taken_in_charge_at = maintenant. Aucun changement si l'incident est déjà
    engagé (idempotent côté état). Renvoie True si une transition a eu lieu.

    NB : « l'organisation devient leader » est représenté par incident.taken_by
    (un User) — le modèle n'a pas de FK organisation directe sur Incident ; on
    réutilise donc taken_by, comme TakeInChargeView et HandleIncidentView.
    """
    if incident.etat == DECLARED:
        incident.etat = TAKEN
        incident.taken_by = leader
        incident.taken_in_charge_at = timezone.now()
        # Anti-gel (spec T3) : (re)prise en compte => réarmer les avertissements.
        incident.antigel_warned_75 = False
        incident.antigel_warned_90 = False
        incident.save(update_fields=[
            'etat', 'taken_by', 'taken_in_charge_at',
            'antigel_warned_75', 'antigel_warned_90',
        ])
        return True
    return False


def terminate_active_collaborations(incident):
    """Clôt les collaborations encore actives d'un incident (spec §5).

    Lorsqu'un incident devient « Résolu (définitif) », ses collaborations encore
    'accepted' passent à 'terminated' (Terminée). Idempotent : ne touche que les
    lignes encore 'accepted', donc relancer ne refait rien. Retourne le nombre
    de collaborations clôturées.
    """
    return Collaboration.objects.filter(
        incident=incident,
        status=COLLAB_STATUS_ACCEPTED,
    ).update(status=COLLAB_STATUS_TERMINATED)


@extend_schema_view(
    get=extend_schema(
        tags=['Incidents'],
        operation_id='incidents_by_zone_list',
        summary="Incidents d'une zone",
        description=(
            "Liste les incidents d'une zone (identifiant numérique). "
            "Authentification requise ; le résultat est restreint selon le rôle web "
            "du demandeur (super admin → tout, org/bureau → interne de son org + public "
            "de son pays, sinon public uniquement)."
        ),
        parameters=[
            OpenApiParameter('zone', OpenApiTypes.INT, OpenApiParameter.PATH,
                             description="Identifiant numérique de la zone."),
        ],
        responses={
            200: IncidentGetSerializer(many=True),
            404: OpenApiResponse(description="Zone/incident introuvable."),
        },
    ),
    post=extend_schema(exclude=True),
)
class IncidentByZoneAPIView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get_permissions(self):
        # La LISTE par zone (GET) est restreinte par rôle (auth requise).
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return []

    def get(self, request, format=None, **kwargs):
        try:
            zone = kwargs['zone']
            base = (
                Incident.objects
                .filter(zone=zone)
                .select_related(
                    'user_id', 'user_id__organisation_member', 'category_id',
                    'taken_by__organisation_member',
                )
                .prefetch_related(
                    'org_assignments__organisation',
                    'collaboration_set__user__organisation_member',
                )
                .order_by('-created_at')
            )
            item = visible_incidents_qs(base, request.user)
            serializer = IncidentGetSerializer(item, many=True)
            return Response(serializer.data)
        except Incident.DoesNotExist:
            return Response(status=404)

@extend_schema_view(
    get=extend_schema(
        tags=['Incidents'],
        operation_id='incidents_retrieve',
        summary="Détail d'un incident",
        description="Récupère un incident par son identifiant (UUID), avec ses "
                    "organisations assignées, catégories et collaborations. Public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
        ],
        responses={200: IncidentSerializer, 404: OpenApiResponse(description="Incident non trouvé.")},
    ),
    put=extend_schema(
        tags=['Incidents'],
        operation_id='incidents_update',
        summary="Mettre à jour un incident",
        description="Remplace les données d'un incident. Si `etat` passe à `resolved` "
                    "ou `in_progress`, un email est envoyé au reporter.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
        ],
        request=IncidentSerializer,
        responses={
            200: IncidentSerializer,
            400: OpenApiResponse(description="Données invalides."),
            404: OpenApiResponse(description="Incident non trouvé."),
        },
    ),
    delete=extend_schema(
        tags=['Incidents'],
        operation_id='incidents_destroy',
        summary="Supprimer un incident (corbeille)",
        description="Suppression logique (is_deleted=True). Réservé au Super Admin ou à "
                    "une organisation propriétaire de l'incident.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
        ],
        responses={
            204: OpenApiResponse(description="Incident supprimé (logique)."),
            403: OpenApiResponse(description="Droits insuffisants."),
            404: OpenApiResponse(description="Incident non trouvé."),
        },
    ),
    post=extend_schema(exclude=True),
)
class IncidentAPIView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get(self, request, id, format=None):
        try:
            # Détail d'un incident : on précharge les org_assignments AVEC leur
            # organisation (select_related) en une requête au lieu d'une requête
            # organisation par assignation, et les catégories (M2M). Sur un pooler
            # distant chaque aller-retour compte (≈80 ms) : 4 requêtes → 3.
            item = (
                Incident.objects
                .select_related('taken_by__organisation_member')
                .prefetch_related(
                    Prefetch(
                        'org_assignments',
                        queryset=IncidentOrgAssignment.objects.select_related('organisation'),
                    ),
                    'category_ids',
                    'collaboration_set__user__organisation_member',
                )
                .get(pk=id)
            )
            serializer = IncidentSerializer(item)
            return Response(serializer.data)
        except Incident.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = Incident.objects.get(pk=id)
        except Incident.DoesNotExist:
            return Response(status=404)
        serializer = IncidentSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            if request.data['etat'] and request.data['etat'] == 'resolved':
                 if serializer.data['user_id']:
                    user = User.objects.get(id=serializer.data['user_id'])
                    subject, from_email, to = "[MAP ACTION] - Changement de statut d'incident", settings.EMAIL_HOST_USER, user.email
                    html_content = render_to_string('mail_incident_resolu.html', {
                        'incident': serializer.data['title']})
                    text_content = strip_tags(
                        html_content)
                    msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
                    msg.attach_alternative(html_content, "text/html")
                    msg.send()
            if request.data['etat'] and request.data['etat'] == 'in_progress':
                  if serializer.data['user_id']:
                    user = User.objects.get(id=serializer.data['user_id'])
                    subject, from_email, to = "[MAP ACTION] - Changement de statut d'incident", settings.EMAIL_HOST_USER, user.email
                    html_content = render_to_string('mail_incident_trait.html', {
                        'incident': serializer.data['title']})
                    text_content = strip_tags(
                        html_content)
                    msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
                    msg.attach_alternative(html_content, "text/html")
                    msg.send()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = Incident.objects.get(pk=id)
        except Incident.DoesNotExist:
            return Response(status=404)
        
        # Vérifier les permissions: Super Admin (tous) ou Organisation (ses incidents seulement)
        permission = IsSuperAdminOrOrgOwnIncident()
        if not permission.has_object_permission(request, self, item):
            return Response({"error": permission.message}, status=403)
        
        item.is_deleted = True
        item.deleted_at = timezone.now()
        item.save(update_fields=['is_deleted', 'deleted_at'])
        return Response(status=204)

@extend_schema_view(
    get=extend_schema(
        tags=['Incidents'],
        operation_id='incidents_list',
        summary="Lister les incidents",
        description="Liste paginée des incidents, restreinte selon le rôle web du "
                    "demandeur (authentification requise).",
        parameters=[
            OpenApiParameter('page', OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Numéro de page."),
            OpenApiParameter('page_size', OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Taille de page."),
        ],
        responses={200: IncidentGetSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Incidents'],
        operation_id='incidents_create',
        summary="Déclarer un incident",
        description="Crée un incident (déclaration citoyenne/mobile, public). Crée la zone "
                    "si nécessaire, +1 point au reporter, déclenche l'analyse IA (Prediction) "
                    "et la conversion vidéo éventuelle.",
        request=IncidentSerializer,
        responses={
            201: IncidentSerializer,
            400: OpenApiResponse(description="Données invalides ou champ `zone` manquant."),
        },
    ),
)
class IncidentAPIListView(generics.CreateAPIView):
    permission_classes = ()

    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get_permissions(self):
        # La LISTE (GET) est restreinte par rôle (auth requise) ; la création POST
        # reste ouverte (déclaration mobile/citoyen, inchangée).
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return []

    def get(self, request, format=None):
        base = (
            Incident.objects
            .select_related(
                'category_id', 'user_id', 'user_id__organisation_member',
                'taken_by__organisation_member',
            )
            .prefetch_related(
                'user_id__zones',
                'category_ids',
                'org_assignments__organisation',
                'collaboration_set__user__organisation_member',
            )
            .order_by('-created_at')
        )
        items = visible_incidents_qs(base, request.user)
        # Recherche + filtres (onglet incidents) : ?search= (titre/description/zone),
        # ?etat= (statut), ?severity=. Combinables.
        p = request.query_params
        search = (p.get('search') or '').strip()
        if search:
            ua = deaccent(search)
            items = items.filter(
                Q(title__unaccent__icontains=ua) | Q(description__unaccent__icontains=ua) | Q(zone__unaccent__icontains=ua)
            )
        etat = p.get('etat') or p.get('status')
        if etat:
            items = items.filter(etat=etat)
        severity = p.get('severity')
        if severity:
            items = items.filter(severity=severity)
        paginator = IncidentPagination()
        result_page = paginator.paginate_queryset(items, request)
        # context={'request'} : nécessaire pour le champ `my_collaboration`
        # (demande de collaboration du viewer sur chaque incident).
        serializer = IncidentGetSerializer(result_page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        serializer = IncidentSerializer(data=request.data)
        
        # Validate serializer
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        # Process zone
        lat = request.data.get("lattitude", "")
        lon = request.data.get("longitude", "")
        zone_name = request.data.get("zone")
        
        if not zone_name:
            return Response({"zone": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)
            
        zone, created = Zone.objects.get_or_create(name=zone_name, defaults={'lattitude': lat, 'longitude': lon})
        
        serializer.save()

        image_name = serializer.data.get("photo")
        print("Image Name:", image_name)

        longitude = serializer.data.get("longitude")
        latitude = serializer.data.get("lattitude")
        print("Longitude:", longitude)

        # Points system from dev version
        if "user_id" in request.data:
            try:
                user = User.objects.get(id=request.data["user_id"])
                user.points += 1
                user.save()
            except User.DoesNotExist:
                print(f"Warning: No user found with ID {request.data['user_id']}")
            except ValueError:
                print(f"Warning: Invalid user ID format: {request.data['user_id']}")

        # Video conversion
        if "video" in request.data and request.data["video"]:
            try:
                subprocess.check_call(['python', f"{settings.BASE_DIR}" + '/convertvideo.py'])
            except subprocess.CalledProcessError as e:
                print(f"Warning: Video conversion failed: {e}")
            except Exception as e:
                print(f"Warning: Unexpected error during video conversion: {e}")

        # --- Trigger AI model-deploy analysis (async via Celery) ---
        # We create a pending Prediction immediately so the front-end can poll
        # GET /MapApi/incidents/<id>/prediction/ and observe status transitions.
        incident_obj = serializer.instance
        if incident_obj is not None:
            prediction, _ = Prediction.objects.get_or_create(
                incident=incident_obj,
                defaults={'status': PredictionStatus.PENDING},
            )
            if incident_obj.photo:
                try:
                    analyze_incident_with_model_task.delay(prediction.id)
                except Exception as e:  # broker unavailable, etc.
                    print(f"Warning: could not enqueue analyze task: {e}")
            else:
                # No photo => mark prediction as failed right away.
                prediction.status = PredictionStatus.FAILED
                prediction.error_message = "Incident has no photo."
                prediction.save(update_fields=['status', 'error_message', 'updated_at'])

        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_mine_list',
    summary="Mes incidents déclarés",
    description="Incidents reportés par l'utilisateur connecté (authentification requise).",
    responses={200: IncidentGetSerializer(many=True)},
    ),
)
class MyIncidentsView(generics.ListAPIView):
    """GET /my-incidents/ — incidents reportés par l'utilisateur connecté."""
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentGetSerializer
    pagination_class = IncidentPagination

    def get_queryset(self):
        return (
            Incident.objects
            .filter(user_id=self.request.user)
            .select_related('user_id', 'category_id')
            .order_by('-created_at')
        )


@extend_schema_view(
    get=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_org_list',
    summary="Incidents de mon organisation",
    description="Incidents liés à l'organisation de l'utilisateur connecté, en mode de prise "
                "en charge interne. Filtrable par origine du reporter.",
    parameters=[
        OpenApiParameter('source', OpenApiTypes.STR, OpenApiParameter.QUERY,
                         enum=['agents_or_internal', 'agents', 'internal', 'citizens', 'all'], required=False,
                         description="agents_or_internal (défaut) = interne + signalés par mes agents ; "
                                     "agents = signalés par mes agents ; internal = pris en charge en interne ; "
                                     "citizens = internes signalés par des citoyens ; all = union."),
        OpenApiParameter('search', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         description="Recherche dans le titre, la description et la localisation (zone)."),
        OpenApiParameter('status', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         enum=['declared', 'taken_into_account', 'in_progress', 'resolved'],
                         description="Filtre par statut (etat) de l'incident. Alias : ?etat=."),
    ],
    responses={200: IncidentGetSerializer(many=True)},
    ),
)
class OrgIncidentsView(generics.ListAPIView):
    """GET /org-incidents/ — incidents liés à l'organisation de l'utilisateur.

    ?source=agents  → incidents reportés par les agents de terrain de l'org
    ?source=citizens → incidents reportés par les citoyens (tous les autres)
    ?source=all (défaut) → tous
    """
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentGetSerializer
    pagination_class = IncidentPagination

    def get_queryset(self):
        user = self.request.user
        org = user.organisation_member

        if not org:
            return Incident.objects.none()

        source = (self.request.query_params.get('source') or 'agents_or_internal').lower()
        mode = (self.request.query_params.get('mode') or '').lower()
        # IDs des agents de terrain de l'org
        agent_ids = list(org.members.filter(org_role=ORG_ROLE_FIELD).values_list('id', flat=True))

        # « Mes interventions » = ce que MON organisation gère réellement :
        #   - interne : incident pris en charge EN INTERNE par mon org
        #               (take_in_charge_mode='internal' ET taken_by ∈ mon org), ET
        #   - agents  : incident SIGNALÉ par un agent de terrain de mon org.
        # Le scope par org (taken_by / reporter) est essentiel : sans lui on renvoyait
        # tous les incidents internes de TOUTES les orgs (« peu importe mon org »). Les
        # incidents où mon org ne fait que COLLABORER (taken_by = autre org, mode
        # 'collaborative') sont exclus → ils relèvent de « Mes collaborations ».
        internal_q = Q(take_in_charge_mode__iexact='internal', taken_by__organisation_member=org)
        agents_q = Q(user_id__in=agent_ids)

        if mode == 'internal' or source == 'internal':
            flt = internal_q
        elif source == 'agents':
            flt = agents_q
        elif source == 'citizens':
            # Incidents internes de mon org signalés par des non-agents (citoyens).
            flt = internal_q & ~agents_q
        else:  # 'agents_or_internal' (défaut) | 'all' → union interne + agents
            flt = internal_q | agents_q

        qs = (
            Incident.objects
            .select_related('user_id', 'category_id', 'taken_by__organisation_member')
            .filter(flt)
            .exclude(is_deleted=True)
            .distinct()
        )

        # Recherche (titre / description / localisation=zone) + filtre par statut (etat).
        p = self.request.query_params
        search = (p.get('search') or '').strip()
        if search:
            ua = deaccent(search)
            qs = qs.filter(
                Q(title__unaccent__icontains=ua)
                | Q(description__unaccent__icontains=ua)
                | Q(zone__unaccent__icontains=ua)
            )
        status_etat = p.get('status') or p.get('etat')
        if status_etat:
            qs = qs.filter(etat=status_etat)

        return qs.order_by('-created_at')

    def list(self, request, *args, **kwargs):
        # Ajoute `reports_count` à chaque incident = nombre de rapports de terrain
        # (FieldReport) des agents de MON organisation sur cet incident — la même
        # portée que le panneau « Rapports des agents » (GET /field-reports/?incident=).
        # Une seule requête groupée par page (pas de N+1).
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        objs = list(page) if page is not None else list(queryset)
        serializer = self.get_serializer(objs, many=True)
        data = serializer.data

        org = getattr(request.user, 'organisation_member', None)
        counts = {}
        ids = [o.id for o in objs]
        if ids and org:
            counts = dict(
                FieldReport.objects
                .filter(incident_id__in=ids, agent__organisation_member=org)
                .values('incident_id')
                .annotate(n=Count('id'))
                .values_list('incident_id', 'n')
            )
        for d, o in zip(data, objs):
            d['reports_count'] = counts.get(o.id, 0)

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


def _assigned_agent_dict(assignment):
    """Représentation explicite d'un agent assigné à un incident."""
    ag = assignment.agent
    org = getattr(ag, 'organisation_member', None) if ag else None
    return {
        'id': ag.id if ag else None,
        'name': (f"{ag.first_name or ''} {ag.last_name or ''}".strip() or ag.email) if ag else None,
        'email': ag.email if ag else None,
        'phone': getattr(ag, 'phone', None) if ag else None,
        'org_role': getattr(ag, 'org_role', None) if ag else None,
        'organisation_id': org.id if org else None,
        'organisation_name': org.name if org else None,
        'assignment_status': assignment.status,
        'deadline': assignment.deadline,
    }


@extend_schema_view(
    get=extend_schema(
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_my_interventions_list',
    summary="Mes interventions",
    description="Incidents sur lesquels l'utilisateur (ou son organisation) travaille "
                "réellement (prise en charge perso/org, assignation org acceptée, "
                "collaboration acceptée, ou agent assigné). Chaque incident est enrichi "
                "de `assigned_agents` et `reports_count`. Authentification requise.",
    responses={200: OpenApiResponse(
        response=IncidentGetSerializer(many=True),
        description="Liste d'incidents (IncidentGetSerializer) enrichis de "
                    "`assigned_agents`[{id,name,email,phone,org_role,organisation_id,"
                    "organisation_name,assignment_status,deadline}] et `reports_count`.",
    )},
    ),
)
class MyInterventionsView(APIView):
    """GET /my-interventions/ — incidents sur lesquels l'utilisateur (ou son
    organisation) travaille réellement, chacun avec TOUS les agents assignés et
    le nombre de rapports. Les rapports détaillés d'un incident sont servis par
    GET /incidents/<id>/reports/.

    « Travaille dessus » = a pris l'incident en charge (perso ou via son org),
    org assignée et acceptée, collaboration acceptée de son org, ou agent assigné.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from ..services.incident_orgs import org_acting_q

        incidents = (
            Incident.objects.filter(org_acting_q(request.user))
            .exclude(is_deleted=True)
            .distinct()
            .select_related('taken_by__organisation_member', 'user_id', 'category_id')
            .prefetch_related(
                'org_assignments__organisation',
                'collaboration_set__user__organisation_member',
                'assignments__agent__organisation_member',
                'incident_rapport',
            )
            .order_by('-created_at')
        )

        data = []
        for inc in incidents:
            inc_data = IncidentGetSerializer(inc).data
            inc_data['assigned_agents'] = [_assigned_agent_dict(a) for a in inc.assignments.all()]
            inc_data['reports_count'] = len(inc.incident_rapport.all())
            data.append(inc_data)
        return Response(data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_reports_list',
    summary="Rapports d'un incident",
    description="Tous les rapports d'agents liés à l'incident (via FK ou M2M), avec "
                "auteur et organisation. Authentification requise.",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    responses={
        200: IncidentReportSerializer(many=True),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class IncidentReportsView(APIView):
    """GET /incidents/<incident_id>/reports/ — tous les rapports d'agents liés à
    l'incident (FK incident OU M2M incidents), avec auteur + organisation.
    Sert la page Mes interventions ET le détail de collaboration (rapports des
    agents de chaque organisation travaillant sur l'incident)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)
        reports = (
            Rapport.objects
            .filter(Q(incident=incident) | Q(incidents=incident))
            .select_related('user_id', 'user_id__organisation_member')
            .distinct()
            .order_by('-created_at')
        )
        return Response(
            IncidentReportSerializer(reports, many=True).data,
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='incidents_assignments_list',
        summary="Lister les assignations d'un incident",
        description="Liste les agents de terrain assignés à l'incident. Réservé au staff "
                    "ou à un admin/bureau de l'organisation propriétaire de l'incident.",
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
        ],
        responses={
            200: IncidentAssignmentSerializer(many=True),
            403: OpenApiResponse(description="Droits insuffisants."),
            404: OpenApiResponse(description="Incident non trouvé."),
        },
    ),
    post=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='incidents_assignments_create',
        summary="Assigner un incident à un agent",
        description="Assigne un agent de terrain à l'incident et lui envoie un email. "
                    "Réservé à un administrateur d'organisation (ou Super Admin).",
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
        ],
        request=IncidentAssignmentSerializer,
        responses={
            201: IncidentAssignmentSerializer,
            400: OpenApiResponse(description="Données invalides."),
            403: OpenApiResponse(description="Droits insuffisants (admin d'organisation requis)."),
            404: OpenApiResponse(description="Incident non trouvé."),
        },
    ),
)
class IncidentAssignmentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentAssignmentSerializer

    def get_queryset(self):
        return IncidentAssignment.objects.filter(
            incident_id=self.kwargs['incident_id']
        ).select_related('incident', 'agent', 'assigned_by').order_by('deadline', '-created_at')

    def list(self, request, *args, **kwargs):
        try:
            incident = Incident.objects.get(pk=self.kwargs['incident_id'])
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if not self._can_manage_assignment(request.user, incident):
            return Response({"error": "Droits insuffisants."}, status=status.HTTP_403_FORBIDDEN)

        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        try:
            incident = Incident.objects.get(pk=self.kwargs['incident_id'])
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        # Assigner un incident à un agent de terrain = staff/super admin, OU
        # Admin d'organisation OU agent de bureau de l'organisation propriétaire de
        # l'incident (cf. _can_manage_assignment). L'agent de bureau gère les agents
        # de terrain de son org (création/édition/suppression… et assignation).
        # Le serializer garantit que l'agent assigné est bien un agent de terrain.
        if not self._can_manage_assignment(request.user, incident):
            return Response(
                {"error": "Vous n'avez pas les droits pour assigner cet incident à un agent."},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data.copy()
        data['incident'] = incident.id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save(assigned_by=request.user)

        # Notifier l'agent par email de sa nouvelle mission
        self._send_assignment_email(assignment, request)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _send_assignment_email(assignment, request):
        agent = assignment.agent
        if not agent or not agent.email:
            return
        incident = assignment.incident
        assigned_by = assignment.assigned_by

        category_name = None
        try:
            if incident.category_id:
                category_name = incident.category_id.name
        except Exception:
            category_name = None

        org_name = None
        if assigned_by and assigned_by.organisation_member:
            org_name = assigned_by.organisation_member.name

        context = {
            'first_name': agent.first_name or '',
            'last_name': agent.last_name or '',
            'incident_title': incident.title or f"Incident #{incident.id}",
            'incident_zone': incident.zone or '',
            'incident_description': incident.description or '',
            'incident_category': category_name or '',
            'incident_etat': incident.etat or '',
            'deadline': assignment.deadline.strftime('%d/%m/%Y à %H:%M') if assignment.deadline else 'Non définie',
            'assigned_by_name': (
                f"{assigned_by.first_name or ''} {assigned_by.last_name or ''}".strip()
                or (assigned_by.email if assigned_by else 'Map Action')
            ),
            'organisation_name': org_name or '',
        }
        try:
            send_email.delay(
                subject="🎯 Nouvelle mission assignée - Map Action",
                template_name='emails/agent_assignment_email.html',
                context=context,
                to_email=agent.email,
            )
            logger.info(
                f"Email d'assignation envoyé (queue Celery) à {agent.email} "
                f"pour l'assignation {assignment.id} sur l'incident {incident.id}"
            )
        except Exception as e:
            logger.error(
                f"Erreur envoi email d'assignation à {agent.email}: {e}",
                exc_info=True,
            )

    @staticmethod
    def _can_manage_assignment(user, incident):
        if user.is_staff or user.is_superuser:
            return True
        # Admin d'org ET agent de bureau gèrent les agents de terrain de leur org.
        if user.org_role not in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]:
            return False
        if not user.organisation_member:
            return False
        org = user.organisation_member
        # 1) Incident de MON organisation : signalé par mon org, ou pris en charge par mon org.
        if incident.user_id and incident.user_id.organisation_member == org:
            return True
        if incident.taken_by and incident.taken_by.organisation_member == org:
            return True
        # 2) Incident PUBLIC encore NON pris en charge (taken_by=None) : n'importe quelle
        #    organisation peut y dépêcher un de ses agents de terrain (investigation d'un
        #    signalement citoyen). Dès qu'une org le prend en charge, seul elle gère (cas 1).
        if getattr(incident, 'is_public', False) and incident.taken_by_id is None:
            return True
        return False


_ASSIGNMENT_DETAIL_PARAMS = [
    OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                     description="Identifiant de l'incident."),
    OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH,
                     description="Identifiant de l'assignation."),
]


@extend_schema_view(
    get=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='incidents_assignments_retrieve',
        summary="Détail d'une assignation",
        description="Récupère une assignation d'agent. Réservé au staff ou à un "
                    "admin/bureau de l'organisation propriétaire de l'incident.",
        parameters=_ASSIGNMENT_DETAIL_PARAMS,
        responses={
            200: IncidentAssignmentSerializer,
            403: OpenApiResponse(description="Droits insuffisants."),
            404: OpenApiResponse(description="Assignation non trouvée."),
        },
    ),
    put=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='incidents_assignments_update',
        summary="Modifier une assignation",
        description="Met à jour une assignation d'agent (droits de gestion requis).",
        parameters=_ASSIGNMENT_DETAIL_PARAMS,
        request=IncidentAssignmentSerializer,
        responses={
            200: IncidentAssignmentSerializer,
            403: OpenApiResponse(description="Droits insuffisants."),
            404: OpenApiResponse(description="Assignation non trouvée."),
        },
    ),
    patch=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='incidents_assignments_partial_update',
        summary="Modifier partiellement une assignation",
        description="Met à jour partiellement une assignation d'agent (droits de gestion requis).",
        parameters=_ASSIGNMENT_DETAIL_PARAMS,
        request=IncidentAssignmentSerializer,
        responses={
            200: IncidentAssignmentSerializer,
            403: OpenApiResponse(description="Droits insuffisants."),
            404: OpenApiResponse(description="Assignation non trouvée."),
        },
    ),
    delete=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='incidents_assignments_destroy',
        summary="Supprimer une assignation",
        description="Supprime une assignation d'agent (droits de gestion requis).",
        parameters=_ASSIGNMENT_DETAIL_PARAMS,
        responses={
            204: OpenApiResponse(description="Assignation supprimée."),
            403: OpenApiResponse(description="Droits insuffisants."),
            404: OpenApiResponse(description="Assignation non trouvée."),
        },
    ),
)
class IncidentAssignmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentAssignmentSerializer

    def get_queryset(self):
        return IncidentAssignment.objects.filter(
            incident_id=self.kwargs['incident_id']
        ).select_related('incident', 'agent', 'assigned_by')

    def get_object(self):
        obj = super().get_object()
        if not IncidentAssignmentListCreateView._can_manage_assignment(self.request.user, obj.incident):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Droits insuffisants.")
        return obj


@extend_schema_view(
    get=extend_schema(
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_agent_assigned_list',
    summary="Incidents assignés à l'agent connecté",
    description="Assignations de l'agent de terrain connecté (réservé aux agents de "
                "terrain ; vide pour les autres rôles).",
    responses={200: IncidentAssignmentSerializer(many=True)},
    ),
)
class AgentAssignedIncidentsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentAssignmentSerializer

    def get_queryset(self):
        user = self.request.user
        if user.org_role != ORG_ROLE_FIELD:
            return IncidentAssignment.objects.none()
        return IncidentAssignment.objects.filter(agent=user).select_related('incident', 'agent', 'assigned_by')


@extend_schema_view(
    get=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='field_reports_list',
        summary="Lister les rapports de terrain",
        description="Rapports de visite terrain, filtrés selon le rôle (staff → tous, "
                    "agent de terrain → les siens, sinon ceux de son organisation). "
                    "Filtre optionnel `?incident=<uuid>` pour n'avoir que les rapports "
                    "des agents sur un incident donné. **Paginé** (`{count, next, previous, "
                    "results}`, 10/page par défaut) : pour un bouton « charger plus », "
                    "suivre `next` (ou `?page=`) jusqu'à `next: null`. Taille de lot via "
                    "`?page_size=`.",
        parameters=[
            OpenApiParameter('incident', OpenApiTypes.UUID, OpenApiParameter.QUERY,
                             description="Ne renvoyer que les rapports de terrain de cet incident."),
        ],
        responses={200: FieldReportSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Prise en charge & Collaboration'],
        operation_id='field_reports_create',
        summary="Créer un rapport de terrain",
        description="Crée un rapport de visite (multipart, champ `photo`). Réservé aux "
                    "agents de terrain pour un incident qui leur est assigné ; passe "
                    "l'assignation correspondante à l'état `reported`.",
        request=FieldReportSerializer,
        responses={
            201: FieldReportSerializer,
            400: OpenApiResponse(description="Données invalides."),
            403: OpenApiResponse(description="Réservé aux agents de terrain assignés."),
            404: OpenApiResponse(description="Incident non trouvé."),
        },
    ),
)
class FieldReportListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FieldReportSerializer
    # Pagination « charger plus » : réponse {count, next, previous, results}.
    # Le front suit `next` jusqu'à null. Taille de lot réglable via ?page_size=.
    pagination_class = FieldReportPagination

    def get_queryset(self):
        user = self.request.user
        qs = FieldReport.objects.select_related('incident', 'agent').order_by('-visited_at')
        # Portée par rôle (staff → tous ; agent terrain → les siens ; sinon ceux de son org)
        if user.is_staff or user.is_superuser:
            pass
        elif user.org_role == ORG_ROLE_FIELD:
            qs = qs.filter(agent=user)
        elif user.organisation_member:
            qs = qs.filter(agent__organisation_member=user.organisation_member)
        else:
            return FieldReport.objects.none()
        # Filtre optionnel : les rapports de terrain d'UN incident donné.
        incident_id = self.request.query_params.get('incident') or self.request.query_params.get('incident_id')
        if incident_id:
            qs = qs.filter(incident_id=incident_id)
        return qs

    def create(self, request, *args, **kwargs):
        incident_id = request.data.get('incident') or request.data.get('incident_id')
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.org_role != ORG_ROLE_FIELD:
            return Response({"error": "Seuls les agents de terrain peuvent créer des rapports."}, status=status.HTTP_403_FORBIDDEN)

        if not IncidentAssignment.objects.filter(incident=incident, agent=request.user).exists():
            return Response({"error": "Cet incident ne vous est pas assigné."}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(agent=request.user, incident=incident)
        IncidentAssignment.objects.filter(incident=incident, agent=request.user).update(status=ASSIGNMENT_REPORTED)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    post=extend_schema(
    tags=['Authentification'],
    operation_id='agent_login',
    summary="Connexion agent (code agent)",
    description="Connexion d'un agent de terrain via son `agent_code`. Retourne des tokens "
                "JWT (access/refresh) et les infos de l'agent. Public.",
    request=inline_serializer(
        name='AgentCodeLoginRequest',
        fields={'agent_code': drf_serializers.CharField()},
    ),
    responses={
        200: OpenApiResponse(description="Tokens JWT {access, refresh, user{...}}."),
        400: OpenApiResponse(description="agent_code manquant."),
        401: OpenApiResponse(description="Code agent invalide."),
        403: OpenApiResponse(description="Compte désactivé."),
    },
    ),
)
class AgentCodeLoginView(APIView):
    """POST /agent-login/ — login par agent_code, retourne des tokens JWT."""
    permission_classes = []

    def post(self, request):
        agent_code = request.data.get('agent_code')
        if not agent_code:
            return Response(
                {"error": "agent_code est requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(agent_code=agent_code, org_role=ORG_ROLE_FIELD)
        except User.DoesNotExist:
            return Response(
                {"error": "Code agent invalide."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"error": "Ce compte est désactivé."},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "org_role": user.org_role,
                "agent_code": user.agent_code,
                "organisation": user.organisation_member.name if user.organisation_member else None,
            },
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_toggle_public',
    summary="Basculer la visibilité d'un incident",
    description="Bascule le drapeau `is_public` d'un incident. Réservé à l'admin/bureau de "
                "l'organisation du reporter ou au staff. Sans corps de requête.",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=None,
    responses={
        200: OpenApiResponse(description="{status, is_public, message}."),
        403: OpenApiResponse(description="Droits insuffisants."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class ToggleIncidentPublicView(APIView):
    """POST /incidents/<incident_id>/toggle-public/ — bascule is_public."""
    permission_classes = [IsAuthenticated]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        # Seul l'admin/bureau de l'org du reporter ou le leader peut basculer
        reporter = incident.user_id
        if reporter and reporter.organisation_member and user.organisation_member == reporter.organisation_member:
            if user.org_role not in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]:
                return Response(
                    {"error": "Seul un admin ou agent de bureau peut modifier la visibilité."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif not user.is_staff:
            return Response(
                {"error": "Vous n'avez pas les droits sur cet incident."},
                status=status.HTTP_403_FORBIDDEN,
            )

        incident.is_public = not incident.is_public
        incident.save(update_fields=['is_public'])

        return Response({
            "status": "success",
            "is_public": incident.is_public,
            "message": f"Incident {'rendu public' if incident.is_public else 'rendu privé'}.",
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        tags=['Référentiel & Statistiques'],
        operation_id='incidents_resolved_list',
        summary="Incidents résolus",
        description="Liste paginée des incidents à l'état `resolved`. Public.",
        parameters=[
            OpenApiParameter('page', OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Numéro de page."),
            OpenApiParameter('page_size', OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Taille de page."),
        ],
        responses={200: IncidentGetSerializer(many=True)},
    ),
    post=extend_schema(exclude=True),
)
class IncidentResolvedAPIListView(generics.ListAPIView):
    """GET /incidentResolved/ — incidents RÉSOLUS (resolved + resolved_definitive),
    **sauf** ceux que mon organisation gère déjà : pris en charge en interne par mon
    org OU signalés par mes agents de terrain (cf. ``org_own_work_q`` ; ce sont les
    incidents résolus « des autres »). Authentification requise (filtre relatif à
    l'org du demandeur). Paginé."""
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentGetSerializer
    pagination_class = IncidentPagination

    def get_queryset(self):
        return (
            Incident.objects
            .filter(etat__in=RESOLVED_ETATS)
            .exclude(org_own_work_q(self.request.user))
            .exclude(is_deleted=True)
            .select_related('user_id', 'category_id', 'taken_by__organisation_member')
            .distinct()
            .order_by('-created_at')
        )

@extend_schema_view(
    get=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_filter_list',
    summary="Liste filtrée pour la carte du dashboard",
    description="Liste légère d'incidents pour la carte (IncidentMapSerializer, avec "
                "`severity`). Le paramètre `scope` et le filtre de date `filter_type` se "
                "combinent. `scope=mine` requiert l'authentification ; les autres scopes "
                "sont publics.",
    parameters=[
        OpenApiParameter(
            'scope', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
            enum=['all', 'mine', 'resolved', 'unresolved'],
            description="all/tous (défaut) ; mine/interne = incidents que l'org du "
                        "demandeur traite (auth requise) ; resolved/resolu ; "
                        "unresolved/non_resolu.",
        ),
        OpenApiParameter(
            'filter_type', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
            enum=['today', 'yesterday', 'last_7_days', 'last_30_days',
                  'this_month', 'last_month', 'custom_range'],
            description="Fenêtre de date sur created_at. `custom_range` exige "
                        "`custom_start` et `custom_end`.",
        ),
        OpenApiParameter('custom_start', OpenApiTypes.DATE, OpenApiParameter.QUERY,
                         required=False, description="Début (YYYY-MM-DD) si filter_type=custom_range."),
        OpenApiParameter('custom_end', OpenApiTypes.DATE, OpenApiParameter.QUERY,
                         required=False, description="Fin (YYYY-MM-DD) si filter_type=custom_range."),
    ],
    responses={200: IncidentMapSerializer(many=True)},
    ),
)
class IncidentFilterView(APIView):
    def get(self, request, *args, **kwargs):
        filter_type = request.query_params.get('filter_type')
        custom_start = request.query_params.get('custom_start')
        custom_end = request.query_params.get('custom_end')
        # scope : un seul URL pour la carte du dashboard (cf. #4).
        #   all/tous (défaut) | mine/interne | resolved/resolu | unresolved/non_resolu
        scope = (request.query_params.get('scope') or 'all').lower()

        # Carte du dashboard : on ne tire que les colonnes scalaires utiles aux
        # marqueurs (cf. IncidentMapSerializer) pour éviter le N+1 d'IncidentSerializer.
        incidents = Incident.objects.only(
            'id', 'title', 'lattitude', 'longitude', 'etat', 'taken_by',
            'is_deleted', 'severity', 'created_at',
        )

        # --- Scope (orthogonal au filtre de date ci-dessous) ---
        resolved_states = [RESOLVED, RESOLVED_DEFINITIVE, IN_VALIDATION]
        if scope in ('mine', 'interne', 'internal'):
            from ..services.incident_orgs import org_acting_q
            if request.user and request.user.is_authenticated:
                incidents = incidents.filter(org_acting_q(request.user)).distinct()
            else:
                incidents = incidents.none()
        elif scope in ('resolved', 'resolu', 'résolu'):
            incidents = incidents.filter(etat__in=resolved_states)
        elif scope in ('unresolved', 'non_resolu', 'non-resolu', 'active'):
            incidents = incidents.exclude(etat__in=resolved_states)
        # scope all/tous : aucun filtre

        if filter_type == 'today':
            incidents = incidents.filter(created_at__date=timezone.now().date())
        elif filter_type == 'yesterday':
            incidents = incidents.filter(created_at__date=timezone.now().date() - timedelta(days=1))
        elif filter_type == 'last_7_days':
            incidents = incidents.filter(created_at__date__gte=timezone.now().date() - timedelta(days=7))
        elif filter_type == 'last_30_days':
            incidents = incidents.filter(created_at__date__gte=timezone.now().date() - timedelta(days=30))
        elif filter_type == 'this_month':
            incidents = incidents.filter(created_at__month=timezone.now().month)
        elif filter_type == 'last_month':
            last_month = timezone.now().month - 1 or 12
            incidents = incidents.filter(created_at__month=last_month)
        elif filter_type == 'custom_range' and custom_start and custom_end:
            incidents = incidents.filter(created_at__date__range=[custom_start, custom_end])

        # --- Filtre pays (optionnel) ---
        # Le front envoie un code pays (`intervention_country` : mali, senegal,
        # burkina_faso, cote_divoire, …). On le fait correspondre au pays GÉOCODÉ de la
        # prédiction (`Prediction.country`) en tolérant les variantes FR/EN et les
        # accents (extension `unaccent`). Un incident sans pays géocodé n'est pas
        # renvoyé quand le filtre est actif (il reste visible dans la vue sans filtre).
        country = (request.query_params.get('country') or '').strip().lower()
        if country:
            names = COUNTRY_GEOCODE_ALIASES.get(country, [deaccent(country.replace('_', ' '))])
            q = Q()
            for name in names:
                q |= Q(prediction__country__unaccent__iexact=name)
            incidents = incidents.filter(q)

        # Pagination OPT-IN pour un chargement progressif de la carte : si ?page ou
        # ?page_size est fourni, on renvoie une page {count, next, previous, results}
        # (marqueurs légers IncidentMapSerializer, ?page_size plafonné à 100) ; sinon
        # la liste brute complète (rétro-compatible avec les consommateurs existants).
        if 'page' in request.query_params or 'page_size' in request.query_params:
            paginator = IncidentPagination()
            page = paginator.paginate_queryset(
                incidents.order_by('-created_at'), request, view=self)
            serializer = IncidentMapSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = IncidentMapSerializer(incidents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
    tags=['Référentiel & Statistiques'],
    operation_id='incidents_dashboard_stats',
    summary="Statistiques du dashboard",
    description="Agrégats KPI calculés côté base pour le dashboard (authentification "
                "requise) : totaux, répartition par localité, catégories, gravité et "
                "activité récente. Ne renvoie jamais la liste complète des incidents.",
    responses={200: OpenApiResponse(description=(
        "{total_alerts, active_responses, resolved_incidents, by_zone[{name,count}], "
        "by_category[{name,count,percentage}], by_severity{high/medium/low:{count,"
        "percentage}}, recent_activity[{id,title,etat,zone,created_at,taken_by}]}."
    ))},
    ),
)
class IncidentDashboardStatsView(APIView):
    """Statistiques agrégées pour le dashboard (cartes KPI + widgets Par Localité /
    Top catégories / Gravité + activité récente).

    Tout est calculé côté BDD via GROUP BY (quelques requêtes), on ne renvoie
    jamais toute la liste d'incidents au client pour qu'il agrège lui-même.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        qs = Incident.objects.filter(is_deleted=False)

        total = qs.count()
        resolved = qs.filter(etat__in=[RESOLVED, RESOLVED_DEFINITIVE]).count()
        active = qs.filter(
            etat__in=[TAKEN, RESOLUTION_PREPARED, IN_VALIDATION, 'in_progress']
        ).count()

        # Par localité : top 5 zones (zone normalisée/trim pour éviter les doublons
        # « Bamako » vs « Bamako » avec espace en trop)
        from django.db.models.functions import Trim
        by_zone = [
            {'name': row['z'], 'count': row['count']}
            for row in (qs.exclude(zone__isnull=True).exclude(zone='')
                          .values(z=Trim('zone')).annotate(count=Count('id'))
                          .order_by('-count'))
            if row['z']
        ][:5]

        # Top catégories (M2M category_ids) : pourcentage du total des incidents
        by_category = [
            {'name': row['category_ids__name'], 'count': row['count'],
             'percentage': round(row['count'] * 100 / total) if total else 0}
            for row in (qs.filter(category_ids__isnull=False)
                          .values('category_ids__name').annotate(count=Count('id'))
                          .order_by('-count')[:5])
        ]

        # Gravité : répartition high/medium/low en pourcentage (somme ≈ 100)
        sev = {row['severity']: row['count']
               for row in qs.values('severity').annotate(count=Count('id'))}
        sev_total = sum(sev.get(l, 0) for l in ('high', 'medium', 'low')) or 1
        by_severity = {
            level: {'count': sev.get(level, 0),
                    'percentage': round(sev.get(level, 0) * 100 / sev_total)}
            for level in ('high', 'medium', 'low')
        }

        # Activité récente : 8 incidents les plus récents
        recent_activity = list(
            qs.order_by('-created_at')[:8]
              .values('id', 'title', 'etat', 'zone', 'created_at', 'taken_by')
        )

        return Response({
            'total_alerts': total,
            'active_responses': active,
            'resolved_incidents': resolved,
            'by_zone': by_zone,
            'by_category': by_category,
            'by_severity': by_severity,
            'recent_activity': recent_activity,
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        tags=['Référentiel & Statistiques'],
        operation_id='incidents_not_resolved_list',
        summary="Incidents non résolus",
        description="Liste paginée des incidents à l'état `declared`. Public.",
        parameters=[
            OpenApiParameter('page', OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Numéro de page."),
            OpenApiParameter('page_size', OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Taille de page."),
        ],
        responses={200: IncidentGetSerializer(many=True)},
    ),
    post=extend_schema(exclude=True),
)
class IncidentNotResolvedAPIListView(generics.ListAPIView):
    """GET /incidentNotResolved/ — incidents NON RÉSOLUS (tout sauf resolved /
    resolved_definitive : declared, taken_into_account, in_progress, in_validation —
    auparavant la vue ne renvoyait QUE 'declared', d'où des incidents manquants),
    **sauf** ceux que mon organisation gère déjà (pris en charge en interne par mon
    org OU signalés par mes agents, cf. ``org_own_work_q``). Auth requise. Paginé."""
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentGetSerializer
    pagination_class = IncidentPagination

    def get_queryset(self):
        return (
            Incident.objects
            .exclude(etat__in=RESOLVED_ETATS)
            .exclude(org_own_work_q(self.request.user))
            .exclude(is_deleted=True)
            .select_related('user_id', 'category_id', 'taken_by__organisation_member')
            .distinct()
            .order_by('-created_at')
        )

@extend_schema_view(
    get=extend_schema(
    tags=['Référentiel & Statistiques'],
    operation_id='incidents_by_month_list',
    summary="Incidents par mois (année courante)",
    description="Incidents de l'année courante, optionnellement filtrés sur un mois. Public.",
    parameters=[
        OpenApiParameter('month', OpenApiTypes.INT, OpenApiParameter.QUERY, required=False,
                         description="Numéro de mois (1-12) ; toute l'année si omis."),
    ],
    responses={
        200: OpenApiResponse(description="{status, message, data:[Incident...]}."),
        400: OpenApiResponse(description="Paramètre month invalide."),
    },
    ),
)
class IncidentByMonthAPIListView(generics.ListAPIView):
    permission_classes = ()
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def list(self, request, *args, **kwargs):
        now = timezone.now()
        month_param = self.request.query_params.get('month', None)
        if month_param:
            try:
                month = int(month_param)
                items = Incident.objects.filter(created_at__year=now.year, created_at__month=month)
            except ValueError:
                return Response({"error": "Invalid month parameter"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            items = Incident.objects.filter(created_at__year=now.year)

        serializer = self.get_serializer(items, many=True)
        return Response({
            "status": "success",
            "message": "Incidents by month",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        tags=['Référentiel & Statistiques'],
        operation_id='incidents_by_month_zone_list',
        summary="Incidents par mois pour une zone",
        description="Répartition mensuelle (total/résolus/non résolus) des incidents "
                    "d'une zone sur l'année courante. Public.",
        parameters=[
            OpenApiParameter('zone', OpenApiTypes.STR, OpenApiParameter.PATH,
                             description="Nom de la zone."),
        ],
        responses={200: OpenApiResponse(
            description="{status, message, data:[{month,total,resolved,unresolved}]}.")},
    ),
    post=extend_schema(exclude=True),
)
class IncidentByMonthByZoneAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get(self, request, format=None, **kwargs):
        zone = kwargs['zone']
        now = timezone.now()
        items = Incident.objects.filter(zone=zone).filter(created_at__year=now.year)
        months = items.datetimes("created_at", kind="month")

        listData = []
        for month in months:
            # month_invs = items.filter(created_at__month=month.month).filter(created_at__year=now.year)
            month_invs = items.filter(created_at__month=month.month)
            month_total = month_invs.count()
            month_resolved = month_invs.filter(etat="resolved").count()
            month_unresolved = month_invs.filter(etat="declared").count()

            # print(f"Month: {month}, Total: {month_total}")
            dataMonth = {"month": month, "total": month_total, "resolved": month_resolved,
                         "unresolved": month_unresolved}
            listData.append(dataMonth)

        return Response({
            "status": "success",
            "message": "incidents by month ",
            "data": listData
        }, status=status.HTTP_200_OK)

@extend_schema_view(
    get=extend_schema(
        tags=['Référentiel & Statistiques'],
        operation_id='incidents_on_week_list',
        summary="Incidents de la semaine (par jour)",
        description="Répartition jour par jour (total/résolus/non résolus) des incidents "
                    "de la dernière semaine. Public.",
        responses={200: OpenApiResponse(
            description="{status, message, data:[{day,total,resolved,unresolved}]}.")},
    ),
    post=extend_schema(exclude=True),
)
class IncidentOnWeekAPIListView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get(self, request, format=None):
        some_day_last_week = timezone.now().date() - timedelta(days=7)
        monday_of_last_week = some_day_last_week - timedelta(days=(some_day_last_week.isocalendar()[2] - 1))
        monday_of_this_week = monday_of_last_week + timedelta(days=8)
        items = Incident.objects.filter(created_at__gte=monday_of_last_week,
                                        created_at__lt=monday_of_this_week).order_by('pk')
        days = items.datetimes("created_at", kind="day")

        listData = []
        for day in days:
            day_invs = items.filter(created_at__day=day.day)
            day_total = day_invs.count()
            day_resolved = day_invs.filter(etat="resolved").count()
            day_unresolved = day_invs.filter(etat="declared").count()
            # print(f"Month: {month}, Total: {month_total}")
            dataDay = {"day": day, "total": day_total, "resolved": day_resolved, "unresolved": day_unresolved}
            listData.append(dataDay)

        return Response({
            "status": "success",
            "message": "incidents by week ",
            "data": listData
        }, status=status.HTTP_200_OK)

@extend_schema_view(
    get=extend_schema(
        tags=['Référentiel & Statistiques'],
        operation_id='incidents_on_week_zone_list',
        summary="Incidents de la semaine pour une zone (par jour)",
        description="Répartition jour par jour (total/résolus/non résolus) des incidents "
                    "d'une zone sur la dernière semaine. Public.",
        parameters=[
            OpenApiParameter('zone', OpenApiTypes.STR, OpenApiParameter.PATH,
                             description="Nom de la zone."),
        ],
        responses={200: OpenApiResponse(
            description="{status, message, data:[{day,total,resolved,unresolved}]}.")},
    ),
    post=extend_schema(exclude=True),
)
class IncidentByWeekByZoneAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get(self, request, format=None, **kwargs):
        zone = kwargs['zone']
        some_day_last_week = timezone.now().date() - timedelta(days=7)
        monday_of_last_week = some_day_last_week - timedelta(days=(some_day_last_week.isocalendar()[2] - 1))
        monday_of_this_week = monday_of_last_week + timedelta(days=8)
        items = Incident.objects.filter(zone=zone).filter(created_at__gte=monday_of_last_week,
                                                          created_at__lt=monday_of_this_week).order_by('pk')
        days = items.datetimes("created_at", kind="day")

        listData = []
        for day in days:
            day_invs = items.filter(created_at__day=day.day)
            day_total = day_invs.count()
            day_resolved = day_invs.filter(etat="resolved").count()
            day_unresolved = day_invs.filter(etat="declared").count()
            # print(f"Month: {month}, Total: {month_total}")
            dataDay = {"day": day, "total": day_total, "resolved": day_resolved, "unresolved": day_unresolved}
            listData.append(dataDay)

        return Response({
            "status": "success",
            "message": "incidents by month ",
            "data": listData
        }, status=status.HTTP_200_OK)

@extend_schema_view(
    get=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_search_list',
    summary="Rechercher des incidents",
    description="Recherche d'incidents dont le titre ou la description contient "
                "`search_term`. Public.",
    parameters=[
        OpenApiParameter('search_term', OpenApiTypes.STR, OpenApiParameter.QUERY,
                         required=True, description="Terme recherché (titre/description)."),
    ],
    responses={
        200: IncidentSerializer(many=True),
        400: OpenApiResponse(description="Paramètre 'search_term' manquant."),
    },
    ),
)
class IncidentSearchView(generics.ListAPIView):
    def get(self, request):
        search_term = request.query_params.get('search_term')
        
        if search_term is None:
            return Response("Parameter 'search_term' is missing", status=status.HTTP_400_BAD_REQUEST)
        
        results = Incident.objects.filter(
            Q(title__icontains=search_term) | Q(description__icontains=search_term)
        )
        serializer = IncidentSerializer(results, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

@extend_schema_view(
    post=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_handle_status',
    summary="Faire avancer le statut d'un incident (legacy)",
    description="Avance l'état d'un incident dans l'ordre `declared` → "
                "`taken_into_account` → `resolved`, et journalise une UserAction. "
                "Authentification requise.",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=inline_serializer(
        name='IncidentHandleStatusRequest',
        fields={'action': drf_serializers.ChoiceField(
            choices=['taken_into_account', 'resolved'])},
    ),
    responses={
        200: OpenApiResponse(description="{status, message, user, action}."),
        400: OpenApiResponse(description="Action invalide ou ordre des états non respecté."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class HandleIncidentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, incident_id, format=None):
        try:
            incident = Incident.objects.get(id=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident not found"}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get("action")

        if action not in ["taken_into_account", "resolved"]:
            return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        if action == "taken_into_account" and incident.etat != "declared":
            return Response({"error": "Incident already taken into account or resolved"}, status=status.HTTP_400_BAD_REQUEST)

        if action == "resolved" and incident.etat != "taken_into_account":
            return Response({"error": "Incident must be taken into account before being resolved"}, status=status.HTTP_400_BAD_REQUEST)

        if action == "taken_into_account":
            incident.etat = "taken_into_account"
            incident.taken_by = user
            action_message = f"a pris en charge l'incident «{incident.title}»."
        elif action == "resolved":
            incident.etat = "resolved"
            action_message = f"a résolu l'incident «{incident.title}»."

        incident.save()

        user_action = UserAction.objects.create(user=user, action=action_message)
        user_data = UserSerializer(user).data
        action_data = UserActionSerializer(user_action).data 
        return Response({
            "status": "success",
            "message": action_message,
            "user": user_data,
            "action": action_data
        }, status=status.HTTP_200_OK)

@extend_schema_view(
    get=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_taken_by_user',
    summary="Utilisateur ayant pris en charge l'incident",
    description="Renvoie l'utilisateur (`taken_by`) ayant pris l'incident en charge. "
                "Authentification requise.",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    responses={
        200: OpenApiResponse(description="{status, user}."),
        404: OpenApiResponse(description="Incident non trouvé ou non pris en charge."),
    },
    ),
)
class IncidentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, incident_id, format=None):
        try:
            incident = Incident.objects.get(id=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident not found"}, status=status.HTTP_404_NOT_FOUND)

        if not incident.taken_by:
            return Response({"error": "Incident not taken into account by any user"}, status=status.HTTP_404_NOT_FOUND)

        user_data = UserSerializer(incident.taken_by).data
        return Response({
            "status": "success",
            "user": user_data
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_take_in_charge',
    summary="Prendre en charge un incident",
    description=(
        "Prise en charge d'un incident (org_admin requis).\n\n"
        "Body JSON :\n"
        "- mode = 'internal' : prise en charge interne (visible uniquement par les membres de l'organisation).\n"
        "- mode = 'collaborative' : prise en charge collaborative ouverte aux autres organisations. "
        "Doit alors préciser role = 'leader' | 'contributor' | 'observer'.\n\n"
        "Règles :\n"
        "- observer est auto-accepté.\n"
        "- contributor est auto-accepté tant qu'aucun leader n'est désigné ; sinon il passe en pending.\n"
        "- leader définit incident.taken_by et remet les contributors déjà acceptés en pending pour validation."
    ),
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=inline_serializer(
        name='IncidentTakeInChargeRequest',
        fields={
            'mode': drf_serializers.ChoiceField(choices=['internal', 'collaborative']),
            'role': drf_serializers.ChoiceField(
                choices=['leader', 'contributor', 'observer'], required=False),
        },
    ),
    responses={
        200: OpenApiResponse(description="{status, message, mode, data:Incident, collaboration}."),
        400: OpenApiResponse(description="mode/role invalide, incident déjà pris en charge ou clôturé, "
                                         "collaboration en doublon, leader déjà désigné."),
        403: OpenApiResponse(description="Droits insuffisants (admin d'organisation requis)."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class TakeInChargeView(APIView):
    """POST /incidents/<incident_id>/take_in_charge/"""
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if incident.is_resolved:
            return Response(
                {"error": "Cet incident est clôturé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mode = (request.data.get('mode') or '').strip().lower()
        if mode not in ('internal', 'collaborative'):
            return Response(
                {"error": "mode requis : 'internal' ou 'collaborative'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ============== MODE INTERNAL ==============
        if mode == 'internal':
            if incident.taken_by is not None or incident.take_in_charge_mode is not None:
                return Response(
                    {"error": "Cet incident a déjà été pris en charge."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if incident.etat != 'declared':
                return Response(
                    {"error": f"Impossible de prendre en charge un incident en état '{incident.etat}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            incident.taken_by = request.user
            incident.etat = 'taken_into_account'
            incident.take_in_charge_mode = 'internal'
            incident.taken_in_charge_at = timezone.now()
            # Anti-gel (spec T3) : (re)prise en compte => réarmer les avertissements.
            incident.antigel_warned_75 = False
            incident.antigel_warned_90 = False
            incident.save(update_fields=[
                'taken_by', 'etat', 'take_in_charge_mode', 'taken_in_charge_at',
                'antigel_warned_75', 'antigel_warned_90',
            ])

            collaboration, _ = Collaboration.objects.get_or_create(
                incident=incident,
                user=request.user,
                defaults={'role': COLLAB_ROLE_LEADER, 'status': 'accepted'},
            )

            action_message = f"a pris en charge l'incident «{incident.title}» en mode interne."
            UserAction.objects.create(user=request.user, action=action_message)

            return Response({
                "status": "success",
                "message": action_message,
                "mode": "internal",
                "data": IncidentSerializer(incident).data,
                "collaboration": CollaborationSerializer(collaboration).data,
            }, status=status.HTTP_200_OK)

        # ============== MODE COLLABORATIVE ==============
        role = (request.data.get('role') or '').strip().lower()
        if role not in (COLLAB_ROLE_LEADER, COLLAB_ROLE_CONTRIBUTOR, COLLAB_ROLE_OBSERVER):
            return Response(
                {"error": "role requis pour le mode collaborative : 'leader', 'contributor' ou 'observer'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Si l'incident est en mode internal, refuser : passer par /collaboration/ pour demander
        if incident.take_in_charge_mode == 'internal':
            return Response(
                {"error": "Cet incident est en mode interne. Faites une demande via POST /collaboration/."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Empêcher doublon de collaboration pour ce user
        existing = Collaboration.objects.filter(incident=incident, user=request.user).first()
        if existing:
            return Response(
                {"error": "Vous avez déjà une collaboration sur cet incident.",
                 "collaboration_id": existing.id,
                 "status": existing.status,
                 "role": existing.role},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Rôle LEADER ---
        if role == COLLAB_ROLE_LEADER:
            if incident.taken_by is not None:
                return Response(
                    {"error": "Un leader est déjà désigné sur cet incident."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            incident.taken_by = request.user
            update_fields = ['taken_by', 'etat', 'take_in_charge_mode']
            if incident.etat == 'declared':
                incident.etat = 'taken_into_account'
                incident.taken_in_charge_at = timezone.now()
                # Anti-gel (spec T3) : (re)prise en compte => réarmer les avertissements.
                incident.antigel_warned_75 = False
                incident.antigel_warned_90 = False
                update_fields += [
                    'taken_in_charge_at', 'antigel_warned_75', 'antigel_warned_90',
                ]
            incident.take_in_charge_mode = 'collaborative'
            incident.save(update_fields=update_fields)

            collaboration = Collaboration.objects.create(
                incident=incident,
                user=request.user,
                role=COLLAB_ROLE_LEADER,
                status='accepted',
            )

            # Remettre en pending les contributors déjà acceptés (le nouveau leader doit les valider)
            reset_count = Collaboration.objects.filter(
                incident=incident,
                role=COLLAB_ROLE_CONTRIBUTOR,
                status='accepted',
            ).exclude(user=request.user).update(status='pending')

            action_message = f"a pris en charge l'incident «{incident.title}» en tant que leader (mode collaboratif)."
            UserAction.objects.create(user=request.user, action=action_message)

            return Response({
                "status": "success",
                "message": action_message,
                "mode": "collaborative",
                "role": role,
                "contributors_reset_to_pending": reset_count,
                "data": IncidentSerializer(incident).data,
                "collaboration": CollaborationSerializer(collaboration).data,
            }, status=status.HTTP_200_OK)

        # --- Rôle OBSERVER ou CONTRIBUTOR ---
        if role == COLLAB_ROLE_OBSERVER:
            collab_status = 'accepted'
        else:  # contributor
            collab_status = 'accepted' if incident.taken_by is None else 'pending'

        collaboration = Collaboration.objects.create(
            incident=incident,
            user=request.user,
            role=role,
            status=collab_status,
        )

        if incident.take_in_charge_mode is None:
            incident.take_in_charge_mode = 'collaborative'
            incident.save(update_fields=['take_in_charge_mode'])

        role_fr = {'contributor': 'contributeur', 'observer': 'observateur', 'leader': 'leader'}.get(role, role)
        action_message = f"a rejoint l'incident «{incident.title}» en tant que {role_fr}."
        UserAction.objects.create(user=request.user, action=action_message)

        return Response({
            "status": "success",
            "message": action_message,
            "mode": "collaborative",
            "role": role,
            "collaboration_status": collab_status,
            "data": IncidentSerializer(incident).data,
            "collaboration": CollaborationSerializer(collaboration).data,
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_close',
    summary="Clôturer un incident",
    description="Clôture un incident (état → `resolved`). Réservé à l'admin/leader de "
                "l'incident. Requiert `resolution_start_date` et `resolution_end_date` ; "
                "toutes les tâches doivent être terminées (done ou failed).",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=inline_serializer(
        name='IncidentCloseRequest',
        fields={
            'resolution_start_date': drf_serializers.DateField(),
            'resolution_end_date': drf_serializers.DateField(),
        },
    ),
    responses={
        200: IncidentSerializer,
        400: OpenApiResponse(description="Dates manquantes, tâches non terminées ou incident déjà clôturé."),
        403: OpenApiResponse(description="Droits insuffisants."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class CloseIncidentView(APIView):
    """POST /incidents/<incident_id>/close/"""
    permission_classes = [IsAuthenticated, IsOrgAdmin, IsIncidentLeader]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if incident.etat == RESOLVED:
            return Response(
                {"error": "Cet incident est déjà clôturé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Dates de résolution obligatoires
        resolution_start = request.data.get('resolution_start_date')
        resolution_end = request.data.get('resolution_end_date')

        if not resolution_start or not resolution_end:
            return Response(
                {"error": "resolution_start_date et resolution_end_date sont obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Vérifier que toutes les tâches sont terminées
        open_tasks = incident.tasks.exclude(state__in=[TASK_DONE, TASK_FAILED])
        if open_tasks.exists():
            return Response(
                {"error": f"Impossible de clôturer : {open_tasks.count()} tâche(s) non terminée(s)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Clôturer
        incident.etat = RESOLVED
        incident.resolution_start_date = resolution_start
        incident.resolution_end_date = resolution_end
        incident.save()
        serializer = IncidentSerializer(incident)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ============================================================================
# Phase 4 — flux de résolution (additif, ne touche pas la voie legacy `close/`)
#   taken_into_account ──prepare-resolution──▶ resolution_prepared
#   resolution_prepared ──return-for-completion──▶ taken_into_account
#   taken_into_account / resolution_prepared ──declare-resolved──▶ in_validation
#   in_validation ──validate-resolution──▶ resolved_definitive
#   in_validation ──reject-resolution(motif)──▶ taken_into_account
# ============================================================================

@extend_schema_view(
    post=extend_schema(
    description=(
        "Préparer une résolution (Agent de bureau / Admin « monte le dossier »). "
        "Exige l'état 'taken_into_account'. Passe l'incident en 'resolution_prepared'."
    ),
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_prepare_resolution',
    summary="Préparer une résolution",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=None,
    responses={
        200: IncidentGetSerializer,
        400: OpenApiResponse(description="État invalide (doit être « Pris en compte »)."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class PrepareResolutionView(APIView):
    """POST /incidents/<incident_id>/prepare-resolution/ — org_admin OU bureau_agent."""
    permission_classes = [IsAuthenticated, IsOrgOperative]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if incident.etat != TAKEN:
            return Response(
                {"error": "Une résolution ne peut être préparée que pour un incident « Pris en compte »."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        incident.etat = RESOLUTION_PREPARED
        incident.resolution_submitted_by = request.user
        incident.resolution_submitted_at = timezone.now()
        incident.save(update_fields=['etat', 'resolution_submitted_by', 'resolution_submitted_at'])

        return Response(IncidentGetSerializer(incident).data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    description=(
        "Renvoyer un dossier de résolution pour complément (Admin). "
        "Exige l'état 'resolution_prepared'. Repasse l'incident en 'taken_into_account'."
    ),
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_return_for_completion',
    summary="Renvoyer pour complément",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=None,
    responses={
        200: IncidentGetSerializer,
        400: OpenApiResponse(description="État invalide (doit être « Résolution préparée »)."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class ReturnForCompletionView(APIView):
    """POST /incidents/<incident_id>/return-for-completion/ — org_admin uniquement."""
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if incident.etat != RESOLUTION_PREPARED:
            return Response(
                {"error": "Seul un dossier « Résolution préparée » peut être renvoyé pour complément."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        incident.etat = TAKEN
        incident.save(update_fields=['etat'])

        return Response(IncidentGetSerializer(incident).data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    description=(
        "Déclarer un incident résolu (Leader / Admin). Déclenche le contrôle Super Admin. "
        "Exige l'état 'taken_into_account' ou 'resolution_prepared'. "
        "Passe l'incident en 'in_validation' et fixe une échéance de validation à 72h."
    ),
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_declare_resolved',
    summary="Déclarer résolu",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=None,
    responses={
        200: IncidentGetSerializer,
        400: OpenApiResponse(description="État invalide (doit être « Pris en compte » ou « Résolution préparée »)."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class DeclareResolvedView(APIView):
    """POST /incidents/<incident_id>/declare-resolved/ — org_admin uniquement."""
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if incident.etat not in (TAKEN, RESOLUTION_PREPARED):
            return Response(
                {"error": "Un incident ne peut être déclaré résolu que s'il est « Pris en compte » "
                          "ou « Résolution préparée »."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        incident.etat = IN_VALIDATION
        incident.validation_deadline = timezone.now() + timedelta(hours=72)
        incident.save(update_fields=['etat', 'validation_deadline'])

        return Response(IncidentGetSerializer(incident).data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_disengage',
    summary="Se désengager d'un incident",
    description="Le leader (Admin d'organisation) se désengage d'un incident « Pris en "
                "compte ». Seul → l'incident repasse « Déclaré » ; sinon le leadership est "
                "proposé aux contributeurs (role=leader, status=pending).",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=None,
    responses={
        200: OpenApiResponse(description="{message, incident:IncidentGetSerializer}."),
        400: OpenApiResponse(description="État invalide (doit être « Pris en compte »)."),
        403: OpenApiResponse(description="Réservé au leader / admin d'organisation."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class DisengageIncidentView(APIView):
    """POST /incidents/<incident_id>/disengage/ — le leader (Admin d'organisation)
    se désengage de l'incident (spec §3, §6).

    - S'il était seul (aucun contributeur accepté) : l'incident repasse « Déclaré ».
    - Sinon : le leadership est proposé aux contributeurs (leur collaboration passe
      role=leader / status=pending) ; l'incident reste « Pris en compte ».
    """
    permission_classes = [IsAuthenticated, IsOrgAdmin, IsIncidentLeader]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if incident.etat != TAKEN:
            return Response(
                {"error": "On ne peut se désengager que d'un incident « Pris en compte »."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Contributeurs acceptés (hors le leader qui se désengage).
        contributors = Collaboration.objects.filter(
            incident=incident,
            role=COLLAB_ROLE_CONTRIBUTOR,
            status=COLLAB_STATUS_ACCEPTED,
        ).exclude(user=request.user)

        # Le leader sortant : on clôt sa propre collaboration et on libère la prise en charge.
        Collaboration.objects.filter(incident=incident, user=request.user).update(
            status=COLLAB_STATUS_TERMINATED
        )
        incident.taken_by = None
        incident.take_in_charge_mode = None
        incident.taken_in_charge_at = None

        if contributors.exists():
            # Leadership proposé aux contributeurs (ils doivent l'accepter).
            contributors.update(role=COLLAB_ROLE_LEADER, status=COLLAB_STATUS_PENDING)
            incident.save(update_fields=['taken_by', 'take_in_charge_mode', 'taken_in_charge_at'])
            message = "Désengagement effectué : le leadership est proposé aux contributeurs."
        else:
            # Seul : l'incident redevient disponible ; les observateurs restants sont clôturés.
            Collaboration.objects.filter(
                incident=incident, status=COLLAB_STATUS_ACCEPTED,
            ).update(status=COLLAB_STATUS_TERMINATED)
            incident.etat = DECLARED
            incident.save(update_fields=['etat', 'taken_by', 'take_in_charge_mode', 'taken_in_charge_at'])
            message = "Désengagement effectué : l'incident repasse « Déclaré »."

        return Response(
            {"message": message, "incident": IncidentGetSerializer(incident).data},
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
    description=(
        "Valider une résolution (Super Admin). "
        "Exige l'état 'in_validation'. Passe l'incident en 'resolved_definitive'."
    ),
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_validate_resolution',
    summary="Valider une résolution",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=None,
    responses={
        200: IncidentGetSerializer,
        400: OpenApiResponse(description="État invalide (doit être « en validation »)."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class ValidateResolutionView(APIView):
    """POST /incidents/<incident_id>/validate-resolution/ — super_admin uniquement."""
    permission_classes = [IsAuthenticated, IsSuperAdminRole]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if incident.etat != IN_VALIDATION:
            return Response(
                {"error": "Seule une résolution « en validation » peut être validée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        incident.etat = RESOLVED_DEFINITIVE
        incident.save(update_fields=['etat'])

        # Spec §5 : à la résolution définitive, les collaborations encore actives
        # passent en « Terminée ». Idempotent.
        terminate_active_collaborations(incident)

        return Response(IncidentGetSerializer(incident).data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    description=(
        "Refuser une résolution (Super Admin). Motif obligatoire. "
        "Exige l'état 'in_validation'. Repasse l'incident en 'taken_into_account' "
        "et enregistre le motif dans rejection_reason."
    ),
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_reject_resolution',
    summary="Refuser une résolution",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=inline_serializer(
        name='IncidentRejectResolutionRequest',
        fields={'motif': drf_serializers.CharField()},
    ),
    responses={
        200: IncidentGetSerializer,
        400: OpenApiResponse(description="Motif manquant ou état invalide (doit être « en validation »)."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class RejectResolutionView(APIView):
    """POST /incidents/<incident_id>/reject-resolution/ — super_admin uniquement."""
    permission_classes = [IsAuthenticated, IsSuperAdminRole]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if incident.etat != IN_VALIDATION:
            return Response(
                {"error": "Seule une résolution « en validation » peut être refusée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        motif = (request.data.get('motif') or '').strip()
        if not motif:
            return Response(
                {"error": "Le motif de refus est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        incident.etat = TAKEN
        incident.rejection_reason = motif
        incident.save(update_fields=['etat', 'rejection_reason'])

        return Response(IncidentGetSerializer(incident).data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    description=(
        "« Signaler à mon Admin » (spec §4). Un agent de bureau recommande un "
        "incident repéré à l'Admin de son organisation. Notifie chaque org_admin "
        "de l'organisation du demandeur, avec un commentaire et un lien vers l'incident."
    ),
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_report_to_admin',
    summary="Signaler un incident à mon Admin",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=inline_serializer(
        name='IncidentReportToAdminRequest',
        fields={'comment': drf_serializers.CharField(required=False)},
    ),
    responses={
        200: OpenApiResponse(description="{status, message, notified_admins, incident_id, link}."),
        400: OpenApiResponse(description="Vous n'êtes rattaché à aucune organisation."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class ReportToAdminView(APIView):
    """POST /incidents/<incident_id>/report-to-admin/ — bureau_agent uniquement."""
    permission_classes = [IsAuthenticated, IsAgentBureau]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        org = getattr(request.user, 'organisation_member', None)
        if org is None:
            return Response(
                {"error": "Vous n'êtes rattaché à aucune organisation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comment = (request.data.get('comment') or '').strip()
        admins = list(org.members.filter(org_role=ORG_ROLE_ADMIN))

        # Lien direct vers la fiche incident (référence dans le message).
        link = f"/incidents/{incident.id}"
        reporter_name = request.user.get_full_name() or request.user.email
        base_msg = (
            f"{reporter_name} vous signale l'incident "
            f"« {incident.title or incident.zone} »."
        )
        if comment:
            base_msg = f"{base_msg} Commentaire : {comment}"
        # Inclure le lien tout en respectant la limite de 255 caractères du champ.
        message = f"{base_msg} ({link})"[:255]

        created = 0
        for admin in admins:
            Notification.objects.create(
                user=admin,
                notif_type='incident_report',
                message=message,
                colaboration=None,
                incident=incident,
            )
            created += 1

        return Response(
            {
                "status": "success",
                "message": "Admin(s) notifié(s).",
                "notified_admins": created,
                "incident_id": incident.id,
                "link": link,
            },
            status=status.HTTP_200_OK,
        )


# ============================================================================
# Phase 4 — assignation d'un incident à une ORGANISATION (Super Admin, spec §2/§3, T5)
#   POST assign-to-organisation/  (Super Admin)  → IncidentOrgAssignment pending, 72 h
#   POST <pk>/accept/  (Admin de l'org cible)    → accepted + engage l'incident
#   POST <pk>/decline/ (Admin de l'org cible)    → declined + motif
#   Tacite (sans réponse à 72 h) → tasks.auto_accept_overdue_assignments (D4)
# ============================================================================

@extend_schema_view(
    post=extend_schema(
    description=(
        "Assigner un incident à une ORGANISATION (Super Admin, spec §2). "
        "Body {\"organisation_id\": ...}. Crée une IncidentOrgAssignment 'pending' "
        "avec une échéance de 72 h, et notifie les Admins de l'organisation cible. "
        "L'incident est assigné à l'organisation, jamais directement à un agent (T5)."
    ),
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_assign_to_organisation',
    summary="Assigner un incident à une organisation",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=inline_serializer(
        name='IncidentAssignToOrgRequest',
        fields={'organisation_id': drf_serializers.UUIDField()},
    ),
    responses={
        201: IncidentOrgAssignmentSerializer,
        400: OpenApiResponse(description="organisation_id manquant/introuvable ou assignation déjà en attente."),
        403: OpenApiResponse(description="Réservé au Super Admin."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class AssignIncidentToOrganisationView(APIView):
    """POST /incidents/<incident_id>/assign-to-organisation/ — super_admin uniquement."""
    permission_classes = [IsAuthenticated, IsSuperAdminRole]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        organisation_id = request.data.get('organisation_id')
        if not organisation_id:
            return Response(
                {"error": "organisation_id est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            organisation = Organisation.objects.get(pk=organisation_id)
        except (Organisation.DoesNotExist, ValueError, TypeError):
            return Response(
                {"error": "Organisation introuvable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Une seule assignation en attente à la fois pour un incident donné.
        if IncidentOrgAssignment.objects.filter(
            incident=incident, status=ORG_ASSIGNMENT_PENDING
        ).exists():
            return Response(
                {"error": "Une assignation est déjà en attente pour cet incident."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assignment = IncidentOrgAssignment.objects.create(
            incident=incident,
            organisation=organisation,
            assigned_by=request.user,
            status=ORG_ASSIGNMENT_PENDING,
            deadline=timezone.now() + timedelta(hours=72),
        )

        # Notifier les Admins de l'organisation cible (colaboration nullable).
        admins = organisation.members.filter(org_role=ORG_ROLE_ADMIN)
        message = (
            f"Le Super Admin vous a assigné l'incident "
            f"« {incident.title or incident.zone} ». À accepter ou décliner sous 72 h."
        )[:255]
        for admin in admins:
            Notification.objects.create(user=admin, notif_type='incident_assignment',
                                        message=message, colaboration=None, incident=incident)

        return Response(
            IncidentOrgAssignmentSerializer(assignment).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    post=extend_schema(
    description=(
        "Accepter une assignation Super Admin (Admin de l'organisation cible, spec §3). "
        "Exige status='pending' et que le demandeur soit Admin de l'organisation "
        "assignée. Passe à 'accepted', fixe responded_at, et engage l'incident "
        "('declared' → 'taken_into_account', taken_by + taken_in_charge_at)."
    ),
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_org_assignment_accept',
    summary="Accepter une assignation d'organisation",
    parameters=[
        OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'IncidentOrgAssignment."),
    ],
    request=None,
    responses={
        200: IncidentOrgAssignmentSerializer,
        400: OpenApiResponse(description="État invalide (doit être « en attente »)."),
        403: OpenApiResponse(description="Vous n'êtes pas Admin de l'organisation assignée."),
        404: OpenApiResponse(description="Assignation non trouvée."),
    },
    ),
)
class AcceptOrgAssignmentView(APIView):
    """POST /incident-org-assignments/<pk>/accept/ — org_admin de l'org cible."""
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def post(self, request, pk):
        try:
            assignment = IncidentOrgAssignment.objects.select_related(
                'incident', 'organisation'
            ).get(pk=pk)
        except IncidentOrgAssignment.DoesNotExist:
            return Response({"error": "Assignation non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        if getattr(request.user, 'organisation_member', None) != assignment.organisation:
            return Response(
                {"error": "Vous n'êtes pas administrateur de l'organisation assignée."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if assignment.status != ORG_ASSIGNMENT_PENDING:
            return Response(
                {"error": "Seule une assignation « en attente » peut être acceptée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assignment.status = ORG_ASSIGNMENT_ACCEPTED
        assignment.responded_at = timezone.now()
        assignment.save(update_fields=['status', 'responded_at'])

        # Engager l'incident (l'organisation en devient responsable / « Pris en compte »).
        engage_incident(assignment.incident, request.user)

        return Response(
            IncidentOrgAssignmentSerializer(assignment).data,
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
    description=(
        "Décliner une assignation Super Admin (Admin de l'organisation cible, spec §3). "
        "Body {\"motif\"/\"reason\"}. Exige status='pending' et que le demandeur soit "
        "Admin de l'organisation assignée. Passe à 'declined', stocke decline_reason, "
        "fixe responded_at."
    ),
    tags=['Prise en charge & Collaboration'],
    operation_id='incidents_org_assignment_decline',
    summary="Décliner une assignation d'organisation",
    parameters=[
        OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'IncidentOrgAssignment."),
    ],
    request=inline_serializer(
        name='IncidentOrgAssignmentDeclineRequest',
        fields={
            'motif': drf_serializers.CharField(required=False),
            'reason': drf_serializers.CharField(required=False),
        },
    ),
    responses={
        200: IncidentOrgAssignmentSerializer,
        400: OpenApiResponse(description="État invalide (doit être « en attente »)."),
        403: OpenApiResponse(description="Vous n'êtes pas Admin de l'organisation assignée."),
        404: OpenApiResponse(description="Assignation non trouvée."),
    },
    ),
)
class DeclineOrgAssignmentView(APIView):
    """POST /incident-org-assignments/<pk>/decline/ — org_admin de l'org cible."""
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def post(self, request, pk):
        try:
            assignment = IncidentOrgAssignment.objects.select_related(
                'incident', 'organisation'
            ).get(pk=pk)
        except IncidentOrgAssignment.DoesNotExist:
            return Response({"error": "Assignation non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        if getattr(request.user, 'organisation_member', None) != assignment.organisation:
            return Response(
                {"error": "Vous n'êtes pas administrateur de l'organisation assignée."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if assignment.status != ORG_ASSIGNMENT_PENDING:
            return Response(
                {"error": "Seule une assignation « en attente » peut être déclinée."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = (request.data.get('motif') or request.data.get('reason') or '').strip()

        assignment.status = ORG_ASSIGNMENT_DECLINED
        assignment.decline_reason = reason or None
        assignment.responded_at = timezone.now()
        assignment.save(update_fields=['status', 'decline_reason', 'responded_at'])

        return Response(
            IncidentOrgAssignmentSerializer(assignment).data,
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_bulk_delete',
    summary="Suppression en masse (corbeille)",
    description="Suppression logique de plusieurs incidents. Vérifie la propriété par "
                "incident (Super Admin ou organisation propriétaire).",
    request=inline_serializer(
        name='IncidentBulkDeleteRequest',
        fields={'incident_ids': drf_serializers.ListField(child=drf_serializers.UUIDField())},
    ),
    responses={
        200: OpenApiResponse(description="{deleted_ids, unauthorized_ids, not_found_ids, message}."),
        400: OpenApiResponse(description="incident_ids doit être une liste non vide."),
    },
    ),
)
class BulkDeleteIncidentsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        incident_ids = request.data.get('incident_ids', [])
        if not isinstance(incident_ids, list) or not incident_ids:
            return Response({"error": "incident_ids doit être une liste non vide."}, status=status.HTTP_400_BAD_REQUEST)

        deleted_ids = []
        unauthorized_ids = []
        not_found_ids = []
        permission = IsSuperAdminOrOrgOwnIncident()

        for incident_id in incident_ids:
            try:
                incident = Incident.objects.get(pk=incident_id)
            except Incident.DoesNotExist:
                not_found_ids.append(incident_id)
                continue

            if not permission.has_object_permission(request, self, incident):
                unauthorized_ids.append(incident_id)
                continue

            if not incident.is_deleted:
                incident.is_deleted = True
                incident.deleted_at = timezone.now()
                incident.save(update_fields=['is_deleted', 'deleted_at'])
            deleted_ids.append(incident_id)

        return Response({
            "deleted_ids": deleted_ids,
            "unauthorized_ids": unauthorized_ids,
            "not_found_ids": not_found_ids,
            "message": f"{len(deleted_ids)} incident(s) supprimé(s)."
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_bulk_restore',
    summary="Restauration en masse (corbeille)",
    description="Restaure plusieurs incidents supprimés (is_deleted=False). Super Admin uniquement.",
    request=inline_serializer(
        name='IncidentBulkRestoreRequest',
        fields={'incident_ids': drf_serializers.ListField(child=drf_serializers.UUIDField())},
    ),
    responses={
        200: OpenApiResponse(description="{restored_ids, not_found_ids, message}."),
        400: OpenApiResponse(description="incident_ids doit être une liste non vide."),
    },
    ),
)
class BulkRestoreIncidentsView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        incident_ids = request.data.get('incident_ids', [])
        if not isinstance(incident_ids, list) or not incident_ids:
            return Response({"error": "incident_ids doit être une liste non vide."}, status=status.HTTP_400_BAD_REQUEST)

        restored_ids = []
        not_found_ids = []

        for incident_id in incident_ids:
            try:
                incident = Incident.objects.get(pk=incident_id, is_deleted=True)
            except Incident.DoesNotExist:
                not_found_ids.append(incident_id)
                continue

            incident.is_deleted = False
            incident.save(update_fields=['is_deleted'])
            restored_ids.append(incident_id)

        return Response({
            "restored_ids": restored_ids,
            "not_found_ids": not_found_ids,
            "message": f"{len(restored_ids)} incident(s) restauré(s)."
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_bulk_force_delete',
    summary="Suppression définitive en masse",
    description="Suppression DÉFINITIVE (hard-delete, irréversible) de plusieurs incidents "
                "déjà en corbeille. Super Admin uniquement.",
    request=inline_serializer(
        name='IncidentBulkForceDeleteRequest',
        fields={'incident_ids': drf_serializers.ListField(child=drf_serializers.UUIDField())},
    ),
    responses={
        200: OpenApiResponse(description="{deleted_ids, not_found_ids, message}."),
        400: OpenApiResponse(description="incident_ids doit être une liste non vide."),
    },
    ),
)
class BulkForceDeleteIncidentsView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        incident_ids = request.data.get('incident_ids', [])
        if not isinstance(incident_ids, list) or not incident_ids:
            return Response({"error": "incident_ids doit être une liste non vide."}, status=status.HTTP_400_BAD_REQUEST)

        deleted_ids = []
        not_found_ids = []

        for incident_id in incident_ids:
            try:
                incident = Incident.objects.get(pk=incident_id, is_deleted=True)
            except Incident.DoesNotExist:
                not_found_ids.append(incident_id)
                continue

            incident.delete()
            deleted_ids.append(incident_id)

        return Response({
            "deleted_ids": deleted_ids,
            "not_found_ids": not_found_ids,
            "message": f"{len(deleted_ids)} incident(s) supprimé(s) définitivement."
        }, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_trash_list',
    summary="Corbeille des incidents",
    description="Liste les incidents supprimés (is_deleted=True). Super Admin uniquement.",
    responses={200: IncidentGetSerializer(many=True)},
    ),
)
class TrashIncidentsView(generics.ListAPIView):
    """GET /incidents/trash/ — liste des incidents supprimés (is_deleted=True)."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = IncidentGetSerializer

    def get_queryset(self):
        return Incident.objects.filter(is_deleted=True).select_related('user_id', 'category_id').order_by('-created_at')


@extend_schema_view(
    post=extend_schema(
    tags=['Incidents'],
    operation_id='incidents_restore',
    summary="Restaurer un incident",
    description="Restaure un incident supprimé (is_deleted=False). Super Admin uniquement.",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=None,
    responses={
        200: IncidentGetSerializer,
        404: OpenApiResponse(description="Incident non trouvé dans la corbeille."),
    },
    ),
)
class RestoreIncidentView(APIView):
    """POST /incidents/<incident_id>/restore/ — restaurer un incident supprimé."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id, is_deleted=True)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé dans la corbeille."}, status=status.HTTP_404_NOT_FOUND)

        incident.is_deleted = False
        incident.save(update_fields=['is_deleted'])
        serializer = IncidentGetSerializer(incident)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
    tags=['Prédiction & IA'],
    operation_id='predictions_incident_retrieve',
    summary="Analyse IA d'un incident",
    description="Récupère l'analyse IA (Prediction) d'un incident : statut et résultat. "
                "Authentification requise.",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    responses={
        200: PredictionSerializer,
        404: OpenApiResponse(description="Incident non trouvé ou aucune prédiction."),
    },
    ),
)
class IncidentPredictionView(APIView):
    """GET /MapApi/incidents/<incident_id>/prediction/ — état + résultat de l'analyse."""
    permission_classes = [IsAuthenticated]

    def get(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        prediction = getattr(incident, 'prediction', None)
        if prediction is None:
            return Response(
                {"error": "Aucune prédiction n'existe pour cet incident."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(PredictionSerializer(prediction).data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
    tags=['Prédiction & IA'],
    operation_id='predictions_incident_retry',
    summary="Relancer l'analyse IA",
    description="Relance la tâche Celery d'analyse IA d'un incident (remet la Prediction "
                "à `pending`). Super Admin uniquement ; nécessite une photo.",
    parameters=[
        OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                         description="Identifiant de l'incident."),
    ],
    request=None,
    responses={
        202: PredictionSerializer,
        400: OpenApiResponse(description="L'incident n'a pas de photo."),
        404: OpenApiResponse(description="Incident non trouvé."),
    },
    ),
)
class RetryIncidentPredictionView(APIView):
    """POST /MapApi/incidents/<incident_id>/prediction/retry/ — relance la task Celery."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        if not incident.photo:
            return Response(
                {"error": "L'incident n'a pas de photo, l'analyse est impossible."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prediction, _ = Prediction.objects.get_or_create(
            incident=incident,
            defaults={'status': PredictionStatus.PENDING},
        )
        prediction.status = PredictionStatus.PENDING
        prediction.error_message = ''
        prediction.save(update_fields=['status', 'error_message', 'updated_at'])

        analyze_incident_with_model_task.delay(prediction.id)
        return Response(PredictionSerializer(prediction).data, status=status.HTTP_202_ACCEPTED)


@extend_schema_view(
    get=extend_schema(
        tags=['Prédiction & IA'],
        operation_id='incident_chat_history',
        summary="Historique du chat IA d'un incident",
        description=(
            "Récupère l'historique des messages (user/assistant) du chat IA de "
            "l'incident, propre à l'utilisateur connecté. Authentification requise.\n\n"
            "Pagination curseur (chargement progressif) : sans `limit`, renvoie tout "
            "l'historique en ordre chronologique. Avec `limit`, renvoie les N messages "
            "les plus récents (ordre croissant) + `has_more` + `next_before`. Pour "
            "charger les messages plus anciens (scroll vers le haut), rappeler avec "
            "`?before=<id du plus ancien message déjà chargé>`."
        ),
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
            OpenApiParameter('limit', OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="Nombre de messages les plus récents à renvoyer (1–100). "
                                         "Absent = tout l'historique."),
            OpenApiParameter('before', OpenApiTypes.UUID, OpenApiParameter.QUERY,
                             description="Curseur : renvoie les messages ANTÉRIEURS à ce message "
                                         "(son id). À utiliser avec `limit` pour le scroll vers le haut."),
        ],
        responses={
            200: OpenApiResponse(
                description="{history:[{id,role,content,created_at,user_id}], has_more, next_before} "
                            "(has_more/next_before présents uniquement quand `limit` est fourni)."),
            400: OpenApiResponse(description="limit invalide, ou 'before' invalide/introuvable."),
            404: OpenApiResponse(description="Incident non trouvé."),
        },
    ),
    post=extend_schema(
        tags=['Prédiction & IA'],
        operation_id='incident_chat_send',
        summary="Envoyer un message au chat IA",
        description="Envoie une question : le serveur appelle le service model-deploy `/chat` "
                    "avec le contexte de la Prediction, puis stocke les messages user et "
                    "assistant. Authentification requise.",
        parameters=[
            OpenApiParameter('incident_id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="Identifiant de l'incident."),
        ],
        request=inline_serializer(
            name='IncidentChatSendRequest',
            fields={'message': drf_serializers.CharField()},
        ),
        responses={
            200: OpenApiResponse(description="{message, history}."),
            400: OpenApiResponse(description="message manquant ou prédiction absente/incomplète."),
            404: OpenApiResponse(description="Incident non trouvé."),
            502: OpenApiResponse(description="Erreur du service de chat IA."),
        },
    ),
)
class IncidentChatView(APIView):
    """GET/POST /MapApi/incidents/<incident_id>/chat/."""
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _serialize_message(m):
        return {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at,
            "user_id": m.user_id,
        }

    def get(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        # Historique privé : limité à l'utilisateur connecté (chaque (user, incident)
        # a sa propre conversation avec l'assistant IA).
        base = incident.chat_messages.filter(
            user=request.user, role__in=[CHAT_ROLE_USER, CHAT_ROLE_ASSISTANT]
        )

        # --- Pagination curseur (chargement progressif du chat) ---
        # Sans `limit` : historique complet, dans l'ordre chronologique (rétro-compatible).
        # Avec `limit` : on renvoie les N messages les PLUS RÉCENTS (ordre chronologique
        # croissant pour l'affichage), + `has_more` et `next_before`. Pour charger les
        # messages plus anciens (scroll vers le haut), rappeler avec
        # `?before=<id du plus ancien message déjà chargé>`.
        limit_param = request.query_params.get('limit')
        if limit_param is None:
            history = base.order_by('created_at', 'id')
            return Response(
                {"history": [self._serialize_message(m) for m in history]},
                status=status.HTTP_200_OK,
            )

        try:
            limit = int(limit_param)
        except (TypeError, ValueError):
            return Response({"detail": "limit doit être un entier."}, status=status.HTTP_400_BAD_REQUEST)
        limit = max(1, min(limit, 100))

        # On pagine du plus récent vers le plus ancien (keyset sur created_at + id).
        qs = base.order_by('-created_at', '-id')

        before = request.query_params.get('before')
        if before:
            try:
                cursor = base.filter(pk=before).values('created_at', 'id').first()
            except (ValueError, ValidationError):
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

        # limit+1 pour savoir s'il reste des messages plus anciens.
        rows = list(qs[:limit + 1])
        has_more = len(rows) > limit
        rows = rows[:limit]
        # rows est en ordre décroissant (récent -> ancien) : le plus ancien de la
        # page est le curseur pour la page suivante (plus ancienne).
        next_before = str(rows[-1].id) if (rows and has_more) else None
        rows.reverse()  # ordre chronologique croissant pour l'affichage
        return Response(
            {
                "history": [self._serialize_message(m) for m in rows],
                "has_more": has_more,
                "next_before": next_before,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        prediction = getattr(incident, 'prediction', None)
        if prediction is None:
            return Response(
                {"detail": "Prediction not found for this incident."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not prediction.full_response:
            return Response(
                {"detail": "Prediction context is empty (analysis not completed yet)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_message = (request.data.get('message') or '').strip()
        if not user_message:
            return Response(
                {"detail": "message is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build the conversation payload from the persisted history — scoped to
        # the current user so the LLM only sees this user's own thread.
        history_qs = incident.chat_messages.filter(
            user=request.user, role__in=[CHAT_ROLE_USER, CHAT_ROLE_ASSISTANT]
        ).order_by('created_at', 'id')
        messages = [{"role": item.role, "content": item.content} for item in history_qs]
        messages.append({"role": CHAT_ROLE_USER, "content": user_message})

        # Persist the user message before calling the LLM so the question
        # is never lost even if the LLM call fails.
        ChatHistory.objects.create(
            incident=incident,
            user=request.user if request.user.is_authenticated else None,
            role=CHAT_ROLE_USER,
            content=user_message,
        )

        try:
            assistant_response = ask_model_chat(
                messages=messages,
                context=prediction.full_response,
            )
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"detail": f"Chat service error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        ChatHistory.objects.create(
            incident=incident,
            user=request.user,  # tie the reply to the asking user → private per-user thread
            role=CHAT_ROLE_ASSISTANT,
            content=assistant_response,
        )

        return Response(
            {
                "message": assistant_response,
                "history": messages + [{
                    "role": CHAT_ROLE_ASSISTANT,
                    "content": assistant_response,
                }],
            },
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
    tags=['Authentification'],
    operation_id='agent_pin_login',
    summary="Connexion agent (téléphone + PIN)",
    description="Connexion d'un agent de terrain via téléphone + PIN 4 chiffres. Retourne "
                "des tokens JWT et `must_change_pin`. Public.",
    request=inline_serializer(
        name='AgentPinLoginRequest',
        fields={
            'phone': drf_serializers.CharField(),
            'pin': drf_serializers.CharField(),
        },
    ),
    responses={
        200: OpenApiResponse(description="Tokens JWT + user{... must_change_pin}."),
        400: OpenApiResponse(description="phone/pin manquant ou aucun PIN configuré."),
        401: OpenApiResponse(description="Téléphone ou PIN invalide."),
    },
    ),
)
class AgentPinLoginView(APIView):
    """POST /agent-pin-login/ — login par téléphone + PIN, retourne tokens JWT."""
    permission_classes = []

    def post(self, request):
        phone = request.data.get('phone')
        pin = request.data.get('pin')
        if not phone or not pin:
            return Response(
                {"error": "phone et pin sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(phone=phone, org_role=ORG_ROLE_FIELD, is_active=True)
        except User.DoesNotExist:
            return Response(
                {"error": "Téléphone invalide ou utilisateur non actif."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.pin_code:
            return Response(
                {"error": "Aucun PIN configuré pour cet agent."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_pin(pin):
            return Response(
                {"error": "PIN invalide."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Générer les tokens JWT
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "org_role": user.org_role,
                    "phone": user.phone,
                    "must_change_pin": user.must_change_pin,
                    "organisation": user.organisation_member.name if user.organisation_member else None,
                },
            },
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
    tags=['Authentification'],
    operation_id='agent_change_pin',
    summary="Changer son PIN (agent)",
    description="Change le PIN de l'agent de terrain connecté. Requiert l'ancien PIN ; le "
                "nouveau doit faire 4 chiffres et ne pas être trivial.",
    request=inline_serializer(
        name='AgentChangePinRequest',
        fields={
            'old_pin': drf_serializers.CharField(),
            'new_pin': drf_serializers.CharField(),
        },
    ),
    responses={
        200: OpenApiResponse(description="PIN changé avec succès."),
        400: OpenApiResponse(description="Champs manquants, aucun PIN configuré ou nouveau PIN invalide/trivial."),
        401: OpenApiResponse(description="Ancien PIN invalide."),
        403: OpenApiResponse(description="Réservé aux agents de terrain."),
    },
    ),
)
class AgentChangePinView(APIView):
    """POST /agent/change-pin/ — changer son PIN (authentifié)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_pin = request.data.get('old_pin')
        new_pin = request.data.get('new_pin')

        if not old_pin or not new_pin:
            return Response(
                {"error": "old_pin et new_pin sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if user.org_role != ORG_ROLE_FIELD:
            return Response(
                {"error": "Cette action est réservée aux agents de terrain."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.pin_code:
            return Response(
                {"error": "Aucun PIN configuré pour cet agent."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_pin(old_pin):
            return Response(
                {"error": "Ancien PIN invalide."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Valider le nouveau PIN : 4 chiffres, pas de PINs trop simples
        if not new_pin.isdigit() or len(new_pin) != 4:
            return Response(
                {"error": "Le nouveau PIN doit être composé de 4 chiffres."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        weak_pins = ['0000', '1234', '1111', '2222', '3333', '4444', '5555', '6666', '7777', '8888', '9999']
        if new_pin in weak_pins:
            return Response(
                {"error": "Ce PIN est trop simple. Choisissez un autre PIN."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Hasher et stocker le nouveau PIN
        from django.contrib.auth.hashers import make_password
        user.pin_code = make_password(new_pin)
        user.must_change_pin = False
        user.save(update_fields=['pin_code', 'must_change_pin'])

        return Response(
            {"message": "PIN changé avec succès."},
            status=status.HTTP_200_OK,
        )
