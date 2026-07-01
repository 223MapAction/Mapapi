"""Organisation & tenant-config endpoints + member management."""
import string
import random
import logging

from Mapapi.views.common import CustomPageNumberPagination, deaccent
from django.db.models import Count, Q

logger = logging.getLogger(__name__)

from rest_framework import status, generics, permissions, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiExample,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes

from ..models import Organisation, User, Incident, ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD, PARTNER_STATUS_ACTIVE
from ..serializer import OrganisationSerializer, OrganisationMemberSerializer
from ..permissions import IsSuperAdminRole
from ..roles import is_super_admin, is_org_admin, is_bureau_agent
from ..Send_mails import send_email


def _active_admin_count(org, exclude_user_id=None):
    """Nombre d'admins (org_admin) actifs d'une organisation, hors `exclude_user_id`."""
    qs = User.objects.filter(
        organisation_member=org,
        org_role=ORG_ROLE_ADMIN,
        is_active=True,
    )
    if exclude_user_id is not None:
        qs = qs.exclude(pk=exclude_user_id)
    return qs.count()


@extend_schema_view(
    list=extend_schema(
        tags=['Organisations & Membres'],
        operation_id='organisations_list',
        summary="Lister les organisations",
        description="Renvoie la liste paginée des organisations. Accès public (aucune authentification requise).",
        parameters=[
            OpenApiParameter('page', OpenApiTypes.INT, OpenApiParameter.QUERY, description="Numéro de page."),
            OpenApiParameter('page_size', OpenApiTypes.INT, OpenApiParameter.QUERY, description="Taille de page (max 1000, défaut 100)."),
        ],
        responses={200: OrganisationSerializer(many=True)},
    ),
    create=extend_schema(
        tags=['Organisations & Membres'],
        operation_id='organisations_create',
        summary="Créer une organisation",
        description="Crée une organisation. Réservé au Super Admin (authentification requise).",
        request=OrganisationSerializer,
        responses={
            201: OrganisationSerializer,
            400: OpenApiResponse(description="Données invalides."),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Réservé au Super Admin."),
        },
    ),
    retrieve=extend_schema(
        tags=['Organisations & Membres'],
        operation_id='organisations_retrieve',
        summary="Détail d'une organisation",
        description="Renvoie une organisation par son identifiant. Accès public.",
        parameters=[OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation.")],
        responses={200: OrganisationSerializer, 404: OpenApiResponse(description="Organisation non trouvée.")},
    ),
    update=extend_schema(
        tags=['Organisations & Membres'],
        operation_id='organisations_update',
        summary="Modifier une organisation (complet)",
        description="Met à jour le profil d'une organisation. Réservé au Super Admin ou à l'Admin de CETTE organisation.",
        parameters=[OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation.")],
        request=OrganisationSerializer,
        responses={
            200: OrganisationSerializer,
            400: OpenApiResponse(description="Données invalides."),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Seul un administrateur de cette organisation (ou Super Admin) peut modifier son profil."),
            404: OpenApiResponse(description="Organisation non trouvée."),
        },
    ),
    partial_update=extend_schema(
        tags=['Organisations & Membres'],
        operation_id='organisations_partial_update',
        summary="Modifier une organisation (partiel)",
        description="Met à jour partiellement le profil d'une organisation. Réservé au Super Admin ou à l'Admin de CETTE organisation.",
        parameters=[OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation.")],
        request=OrganisationSerializer,
        responses={
            200: OrganisationSerializer,
            400: OpenApiResponse(description="Données invalides."),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Seul un administrateur de cette organisation (ou Super Admin) peut modifier son profil."),
            404: OpenApiResponse(description="Organisation non trouvée."),
        },
    ),
    destroy=extend_schema(
        tags=['Organisations & Membres'],
        operation_id='organisations_destroy',
        summary="Supprimer une organisation",
        description="Supprime une organisation. Réservé au Super Admin (authentification requise).",
        parameters=[OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation.")],
        responses={
            204: OpenApiResponse(description="Organisation supprimée."),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Réservé au Super Admin."),
            404: OpenApiResponse(description="Organisation non trouvée."),
        },
    ),
)
class OrganisationViewSet(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = Organisation.objects.all()
    serializer_class = OrganisationSerializer
    permission_classes = []
    pagination_class = CustomPageNumberPagination  # Liste d'orgs sans pagination (généralement peu d'orgs)

    def get_queryset(self):
        # Plus récentes d'abord, ordre stable (corrige le saut de position après édition).
        qs = Organisation.objects.all().order_by('-created_at')
        p = self.request.query_params
        search = (p.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(acronym__icontains=search)
                | Q(subdomain__icontains=search) | Q(intervention_country__icontains=search)
            )
        sector = p.get('activity_sector') or p.get('sector')
        if sector:
            qs = qs.filter(activity_sector=sector)
        statut = p.get('partner_status') or p.get('status')
        if statut:
            qs = qs.filter(partner_status=statut)
        org_type = p.get('organisation_type') or p.get('type')
        if org_type:
            qs = qs.filter(organisation_type=org_type)
        return qs

    def get_permissions(self):
        # Spec §6 :
        #  - création d'organisation        → Super Admin uniquement
        #  - modification du profil d'une org → Admin de CETTE org (vérifié sur l'objet) ou Super Admin
        #  - suppression d'une organisation   → Super Admin uniquement
        #  - lecture (GET)                    → public (inchangé)
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsSuperAdminRole()]
        if self.request.method in ('PUT', 'PATCH'):
            return [IsAuthenticated()]
        if self.request.method == 'DELETE':
            return [IsAuthenticated(), IsSuperAdminRole()]
        return []

    def update(self, request, *args, **kwargs):
        org = self.get_object()
        # Modifier le profil d'une organisation : Super Admin, ou Admin de CETTE organisation.
        if not (
            is_super_admin(request.user)
            or (is_org_admin(request.user) and request.user.organisation_member_id == org.pk)
        ):
            return Response(
                {"error": "Seul un administrateur de cette organisation peut modifier son profil."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)


class NotFieldAgent(permissions.BasePermission):
    """Autorise tout utilisateur authentifié SAUF l'agent de terrain (mobile-only)."""

    message = "Non accessible à l'agent de terrain."

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return is_super_admin(u) or getattr(u, 'org_role', None) != ORG_ROLE_FIELD


@extend_schema(
    tags=['Organisations & Membres'],
    operation_id='organisations_others_list',
    summary='Autres organisations (hors la mienne)',
    description="Liste paginée des organisations SAUF celle de l'utilisateur connecté. "
                "Recherche `?search=` (nom / acronyme / sous-domaine / pays, insensible à la "
                "casse et aux accents). Pagination `?page`/`?page_size` (chargement « en "
                "savoir plus »). Accessible à tous les rôles dashboard SAUF l'agent de terrain.",
    parameters=[
        OpenApiParameter('search', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False,
                         description="Recherche nom / acronyme / sous-domaine / pays."),
        OpenApiParameter('page', OpenApiTypes.INT, OpenApiParameter.QUERY, required=False,
                         description="Numéro de page (chargement progressif « en savoir plus »)."),
        OpenApiParameter('page_size', OpenApiTypes.INT, OpenApiParameter.QUERY, required=False,
                         description="Taille de page."),
    ],
    responses={200: OrganisationSerializer(many=True)},
)
class OtherOrganisationsView(generics.ListAPIView):
    """GET /organisations/others/ — organisations autres que celle du user connecté."""

    serializer_class = OrganisationSerializer
    permission_classes = [NotFieldAgent]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        user = self.request.user
        qs = Organisation.objects.all().order_by('-created_at')
        own = getattr(user, 'organisation_member_id', None)
        if own:
            qs = qs.exclude(id=own)
        search = (self.request.query_params.get('search') or '').strip()
        if search:
            ua = deaccent(search)
            qs = qs.filter(
                Q(name__unaccent__icontains=ua)
                | Q(acronym__unaccent__icontains=ua)
                | Q(subdomain__unaccent__icontains=ua)
                | Q(intervention_country__unaccent__icontains=ua)
            )
        return qs


@extend_schema(
    tags=['Organisations & Membres'],
    operation_id='organisations_stats',
    summary="Stats du dashboard organisations",
    description="Cartes du dashboard organisations : total, actives, inactives, et nombre "
                "total d'incidents pris en compte par des organisations. Accès public.",
    responses={200: inline_serializer(name='OrganisationStats', fields={
        'total': serializers.IntegerField(),
        'active': serializers.IntegerField(),
        'inactive': serializers.IntegerField(),
        'incidents_taken_total': serializers.IntegerField(),
    })},
)
class OrganisationStatsView(APIView):
    """GET /organisations/stats/ — compteurs pour les cartes du dashboard orgs."""
    permission_classes = []

    def get(self, request):
        total = Organisation.objects.count()
        active = Organisation.objects.filter(partner_status=PARTNER_STATUS_ACTIVE).count()
        incidents_taken = Incident.objects.filter(
            taken_by__organisation_member__isnull=False, is_deleted=False
        ).count()
        return Response({
            'total': total,
            'active': active,
            'inactive': total - active,
            'incidents_taken_total': incidents_taken,
        })


@extend_schema_view(get=extend_schema(
    tags=['Organisations & Membres'],
    operation_id='organisations_detail_enriched',
    summary="Détail enrichi d'une organisation",
    description=(
        "Renvoie l'organisation enrichie d'un objet `stats`. Accès public. "
        "`stats` contient : member_count, field_agents_count, bureau_agents_count, "
        "admins_count, incident_count, resolved_incident_count."
    ),
    parameters=[OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation.")],
    responses={
        200: OpenApiResponse(
            response=OrganisationSerializer,
            description="Organisation + objet `stats` (compteurs membres/incidents).",
        ),
        404: OpenApiResponse(description="Organisation non trouvée."),
    },
))
class OrganisationDetailView(APIView):
    """GET /organisations/<int:pk>/detail/ — détail enrichi avec stats."""
    permission_classes = []

    def get(self, request, pk):
        try:
            org = Organisation.objects.get(pk=pk)
        except Organisation.DoesNotExist:
            return Response(
                {"error": "Organisation non trouvée."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Statistiques
        members = org.members.all()
        member_count = members.count()
        field_agents_count = members.filter(org_role=ORG_ROLE_FIELD).count()
        bureau_agents_count = members.filter(org_role=ORG_ROLE_BUREAU).count()
        admins_count = members.filter(org_role=ORG_ROLE_ADMIN).count()

        # Incidents créés par les membres de l'org
        incident_count = Incident.objects.filter(user_id__in=members).count()
        resolved_count = Incident.objects.filter(
            user_id__in=members,
            status=RESOLVED,
        ).count()

        data = OrganisationSerializer(org).data
        data.update({
            "stats": {
                "member_count": member_count,
                "field_agents_count": field_agents_count,
                "bureau_agents_count": bureau_agents_count,
                "admins_count": admins_count,
                "incident_count": incident_count,
                "resolved_incident_count": resolved_count,
            },
        })
        return Response(data, status=status.HTTP_200_OK)


@extend_schema_view(get=extend_schema(
    tags=['Organisations & Membres'],
    operation_id='organisations_tenant_config',
    summary="Configuration de tenant (thème par sous-domaine)",
    description=(
        "Renvoie la configuration de thème de l'organisation résolue à partir du "
        "sous-domaine de la requête. Accès public. 404 si aucune organisation ne "
        "correspond au sous-domaine."
    ),
    responses={
        200: inline_serializer(
            name='TenantConfigResponse',
            fields={
                'name': serializers.CharField(),
                'subdomain': serializers.CharField(),
                'logo_url': serializers.CharField(allow_null=True),
                'primary_color': serializers.CharField(allow_null=True),
                'secondary_color': serializers.CharField(allow_null=True),
                'background_color': serializers.CharField(allow_null=True),
                'is_premium': serializers.BooleanField(),
            },
        ),
        404: OpenApiResponse(description="Organisation introuvable pour ce sous-domaine."),
    },
))
class TenantConfigView(APIView):
    permission_classes = []

    def get(self, request, format=None):
        org = getattr(request, 'organisation', None)
        if org is None:
            return Response({'detail': 'Organisation not found for this subdomain.'}, status=status.HTTP_404_NOT_FOUND)
        logo_url = None
        if org.logo:
            try:
                logo_url = request.build_absolute_uri(org.logo.url)
            except Exception:
                logo_url = org.logo.url if hasattr(org.logo, 'url') else None
        data = {
            'name': org.name,
            'subdomain': org.subdomain,
            'logo_url': logo_url,
            'primary_color': org.primary_color,
            'secondary_color': org.secondary_color,
            'background_color': org.background_color,
            'is_premium': org.is_premium,
        }
        return Response(data)


@extend_schema_view(list=extend_schema(
    tags=['Organisations & Membres'],
    operation_id='organisations_members_list',
    summary="Lister les membres d'une organisation",
    description=(
        "Liste les membres d'une organisation. Authentification requise ; réservé "
        "au staff (is_staff) ou aux org_admin / bureau_agent de CETTE organisation."
    ),
    parameters=[OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation.")],
    responses={
        200: OrganisationMemberSerializer(many=True),
        401: OpenApiResponse(description="Authentification requise."),
        403: OpenApiResponse(description="Droits insuffisants pour voir les membres de cette organisation."),
    },
))
class OrganisationMemberListView(generics.ListAPIView):
    """GET /organisations/<pk>/members/ — liste des membres de l'organisation."""
    serializer_class = OrganisationMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        org_id = self.kwargs['pk']
        return User.objects.filter(organisation_member_id=org_id).order_by('org_role', 'last_name')

    def list(self, request, *args, **kwargs):
        # Vérifier que l'utilisateur est admin ou agent de bureau de cette org
        org_id = self.kwargs['pk']
        user = request.user
        if not (user.is_staff or (
            user.organisation_member_id == org_id
            and user.org_role in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]
        )):
            return Response(
                {"error": "Vous n'avez pas les droits pour voir les membres de cette organisation."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().list(request, *args, **kwargs)


@extend_schema_view(post=extend_schema(
    tags=['Organisations & Membres'],
    operation_id='organisations_members_add',
    summary="Ajouter un membre à une organisation",
    description=(
        "Affecte un utilisateur EXISTANT (`user_id`) à l'organisation avec le rôle "
        "`org_role`. Authentification requise ; réservé au Super Admin ou à l'Admin "
        "de CETTE organisation. Si le rôle est `field_agent` : génère `agent_code`, "
        "un `pin_code` initial (renvoyé une seule fois dans `initial_pin`) et envoie "
        "un email avec les identifiants."
    ),
    parameters=[OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation.")],
    request=inline_serializer(
        name='OrganisationMemberAddRequest',
        fields={
            'user_id': serializers.UUIDField(),
            'org_role': serializers.ChoiceField(choices=[ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD]),
        },
    ),
    examples=[
        OpenApiExample(
            'Ajout agent de terrain',
            value={'user_id': '00000000-0000-0000-0000-000000000000', 'org_role': 'field_agent'},
            request_only=True,
        ),
    ],
    responses={
        201: OpenApiResponse(
            response=OrganisationMemberSerializer,
            description=(
                "Membre affecté. Pour un `field_agent` nouvellement doté d'un PIN, la "
                "réponse ajoute `initial_pin` (PIN en clair, une seule fois), "
                "`must_change_pin` (bool) et `email_sent` (bool ; `email_error` si l'envoi a échoué)."
            ),
        ),
        400: OpenApiResponse(description="user_id et org_role requis, ou rôle invalide."),
        401: OpenApiResponse(description="Authentification requise."),
        403: OpenApiResponse(description="Seul un administrateur d'organisation peut gérer les membres."),
        404: OpenApiResponse(description="Organisation ou utilisateur non trouvé."),
    },
))
class OrganisationMemberCreateView(APIView):
    """POST /organisations/<pk>/members/ — ajouter un membre."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        # Spec §6 : créer/gérer les utilisateurs = Admin d'organisation uniquement
        # (un agent de bureau ne gère plus les membres). Super Admin reste autorisé.
        if not (is_super_admin(user) or (
            user.organisation_member_id == pk
            and is_org_admin(user)
        )):
            return Response(
                {"error": "Seul un administrateur d'organisation peut gérer les membres."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            org = Organisation.objects.get(pk=pk)
        except Organisation.DoesNotExist:
            return Response({"error": "Organisation non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        user_id = request.data.get('user_id')
        org_role = request.data.get('org_role')

        if not user_id or not org_role:
            return Response(
                {"error": "user_id et org_role sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if org_role not in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD]:
            return Response(
                {"error": f"Rôle invalide. Choix : org_admin, bureau_agent, field_agent."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            member = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"error": "Utilisateur non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        # Affecter à l'organisation
        member.organisation_member = org
        member.org_role = org_role

        # Générer un code agent si c'est un agent de terrain
        if org_role == ORG_ROLE_FIELD and not member.agent_code:
            member.generate_agent_code()

        # Générer un PIN initial pour les agents de terrain (à changer à la 1ère connexion)
        initial_pin = None
        if org_role == ORG_ROLE_FIELD and not member.pin_code:
            initial_pin = member.generate_and_set_pin(force_change=True)

        member.save()

        # Envoyer l'email avec le PIN pour les agents de terrain
        email_sent = False
        email_error = None
        if initial_pin is not None and member.email:
            try:
                context = {
                    'first_name': member.first_name,
                    'last_name': member.last_name,
                    'phone': member.phone or 'non renseigné',
                    'pin_code': initial_pin,
                    'organisation_name': org.name,
                }
                send_email.delay(
                    subject='🌍 Bienvenue sur Map Action - Vos identifiants de connexion',
                    template_name='emails/agent_pin_email.html',
                    context=context,
                    to_email=member.email
                )
                email_sent = True
                logger.info(f"Email PIN envoyé (queue Celery) à {member.email} pour l'agent {member.id}")
            except Exception as e:
                email_error = str(e)
                logger.error(f"Erreur envoi email PIN à {member.email}: {e}", exc_info=True)

        serializer = OrganisationMemberSerializer(member)
        response_data = serializer.data
        # Inclure le PIN en clair uniquement lors de la création (pour le communiquer à l'agent)
        if initial_pin is not None:
            response_data['initial_pin'] = initial_pin
            response_data['must_change_pin'] = member.must_change_pin
            response_data['email_sent'] = email_sent
            if email_error:
                response_data['email_error'] = email_error
        return Response(response_data, status=status.HTTP_201_CREATED)


@extend_schema_view(post=extend_schema(
    tags=['Organisations & Membres'],
    operation_id='organisations_agents_create',
    summary="Créer un agent de terrain (tout-en-un)",
    description=(
        "Crée un utilisateur ET l'affecte comme agent de terrain (`field_agent`) de "
        "l'organisation en un seul appel : génère `agent_code` + `pin_code` initial "
        "et envoie l'email d'identifiants. Authentification requise ; réservé au "
        "Super Admin ou à l'Admin de CETTE organisation."
    ),
    parameters=[OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation.")],
    request=inline_serializer(
        name='FieldAgentCreateRequest',
        fields={
            'first_name': serializers.CharField(),
            'last_name': serializers.CharField(),
            'email': serializers.EmailField(),
            'phone': serializers.CharField(),
            'address': serializers.CharField(required=False),
        },
    ),
    examples=[
        OpenApiExample(
            'Création agent de terrain',
            value={
                'first_name': 'Awa', 'last_name': 'Diallo',
                'email': 'awa.diallo@example.com', 'phone': '+221771234567',
                'address': 'Dakar',
            },
            request_only=True,
        ),
    ],
    responses={
        201: OpenApiResponse(
            response=OrganisationMemberSerializer,
            description=(
                "Agent créé. La réponse ajoute toujours `initial_pin` (PIN en clair, "
                "une seule fois), `must_change_pin` (bool) et `email_sent` (bool ; "
                "`email_error` si l'envoi de l'email a échoué)."
            ),
        ),
        400: OpenApiResponse(description="Champs requis manquants, email déjà utilisé, ou téléphone déjà pris par un agent de terrain."),
        401: OpenApiResponse(description="Authentification requise."),
        403: OpenApiResponse(description="Seul un administrateur d'organisation peut créer un agent."),
        404: OpenApiResponse(description="Organisation non trouvée."),
    },
))
class FieldAgentCreateView(APIView):
    """POST /organisations/<pk>/agents/create/

    Endpoint tout-en-un destiné aux admins d'organisation :
    crée l'utilisateur, l'affecte comme agent de terrain, génère
    agent_code + PIN initial, et envoie l'email d'identifiants.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user

        # Créer un agent de TERRAIN = Admin d'org OU agent de bureau de CETTE org
        # (ou Super Admin). Un agent de bureau gère les agents de terrain de son org
        # (création comme suppression) ; la création de staff (admin/bureau) reste,
        # elle, réservée à l'admin d'org via StaffAccountCreateView.
        if not (is_super_admin(user) or (
            user.organisation_member_id == pk
            and (is_org_admin(user) or is_bureau_agent(user))
        )):
            return Response(
                {"error": "Seul un administrateur d'organisation ou un agent de bureau de cette organisation peut créer un agent de terrain."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            org = Organisation.objects.get(pk=pk)
        except Organisation.DoesNotExist:
            return Response({"error": "Organisation non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        first_name = (request.data.get('first_name') or '').strip()
        last_name = (request.data.get('last_name') or '').strip()
        email = (request.data.get('email') or '').strip().lower()
        phone = (request.data.get('phone') or '').strip()
        address = (request.data.get('address') or '').strip()

        # Validation
        missing = [f for f, v in {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
        }.items() if not v]
        if missing:
            # `fields` = liste des champs en erreur (le front peut les surligner) ;
            # `errors` = message par champ ; `error` = résumé lisible (rétro-compat).
            return Response(
                {"error": f"Champs requis manquants : {', '.join(missing)}.",
                 "fields": missing,
                 "errors": {f: "Ce champ est requis." for f in missing}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Email unique
        if User.objects.filter(email=email).exists():
            msg = "Un utilisateur avec cet email existe déjà. Utilise l'endpoint /members/add/ pour l'affecter."
            return Response(
                {"error": msg, "field": "email", "errors": {"email": msg}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Téléphone unique parmi les agents de terrain (sinon login PIN ambigu)
        if User.objects.filter(phone=phone, org_role=ORG_ROLE_FIELD).exists():
            msg = "Un agent de terrain avec ce numéro de téléphone existe déjà."
            return Response(
                {"error": msg, "field": "phone", "errors": {"phone": msg}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Création de l'utilisateur (password aléatoire, l'agent se connecte via PIN)
        random_password = ''.join(random.choices(string.ascii_letters + string.digits, k=24))
        member = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            address=address,
            user_type='field_agent',
            org_role=ORG_ROLE_FIELD,
            organisation_member=org,
            is_active=True,
            is_verified=True,  # créé par admin, pas besoin de vérification email
        )
        member.set_password(random_password)
        member.save()

        # Génération agent_code + PIN
        member.generate_agent_code()
        initial_pin = member.generate_and_set_pin(force_change=True)

        # Envoi de l'email avec le PIN
        email_sent = False
        email_error = None
        try:
            context = {
                'first_name': member.first_name,
                'last_name': member.last_name,
                'phone': member.phone,
                'pin_code': initial_pin,
                'organisation_name': org.name,
            }
            send_email.delay(
                subject='🌍 Bienvenue sur Map Action - Vos identifiants de connexion',
                template_name='emails/agent_pin_email.html',
                context=context,
                to_email=member.email,
            )
            email_sent = True
            logger.info(f"Email PIN envoyé (queue Celery) à {member.email} pour l'agent {member.id}")
        except Exception as e:
            email_error = str(e)
            logger.error(f"Erreur envoi email PIN à {member.email}: {e}", exc_info=True)

        serializer = OrganisationMemberSerializer(member)
        response_data = serializer.data
        response_data.update({
            'initial_pin': initial_pin,
            'must_change_pin': member.must_change_pin,
            'email_sent': email_sent,
        })
        if email_error:
            response_data['email_error'] = email_error
        return Response(response_data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    patch=extend_schema(
        tags=['Organisations & Membres'],
        operation_id='organisations_members_update',
        summary="Modifier un membre d'une organisation",
        description=(
            "Met à jour un membre (email, first_name, last_name, phone, org_role) — "
            "tous les champs sont optionnels. Authentification requise ; réservé au "
            "Super Admin ou à l'Admin de CETTE organisation. Règle anti-verrouillage : "
            "impossible de rétrograder le dernier admin actif de l'organisation."
        ),
        parameters=[
            OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation."),
            OpenApiParameter('user_id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant du membre."),
        ],
        request=inline_serializer(
            name='OrganisationMemberUpdateRequest',
            fields={
                'email': serializers.EmailField(required=False),
                'first_name': serializers.CharField(required=False),
                'last_name': serializers.CharField(required=False),
                'phone': serializers.CharField(required=False),
                'org_role': serializers.ChoiceField(
                    choices=[ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD], required=False,
                ),
            },
        ),
        responses={
            200: OrganisationMemberSerializer,
            400: OpenApiResponse(description="Email déjà utilisé, téléphone déjà pris, rôle invalide, ou dernier admin actif."),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Droits insuffisants."),
            404: OpenApiResponse(description="Membre non trouvé dans cette organisation."),
        },
    ),
    delete=extend_schema(
        tags=['Organisations & Membres'],
        operation_id='organisations_members_remove',
        summary="Retirer un membre d'une organisation",
        description=(
            "Supprime physiquement un membre de l'organisation. Authentification "
            "requise ; réservé au Super Admin ou à l'Admin de CETTE organisation. "
            "Règle anti-verrouillage : impossible de retirer le dernier admin actif. "
            "Renvoie 200 avec un message de confirmation."
        ),
        parameters=[
            OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation."),
            OpenApiParameter('user_id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant du membre."),
        ],
        request=None,
        responses={
            200: OpenApiResponse(description="Agent supprimé avec succès de l'organisation (objet `{message}`)."),
            400: OpenApiResponse(description="Impossible de retirer le dernier administrateur actif de l'organisation."),
            401: OpenApiResponse(description="Authentification requise."),
            403: OpenApiResponse(description="Droits insuffisants."),
            404: OpenApiResponse(description="Membre non trouvé dans cette organisation."),
        },
    ),
)
class OrganisationMemberDetailView(APIView):
    """
    PATCH  /organisations/<pk>/members/<user_id>/ — modifier le rôle
    DELETE /organisations/<pk>/members/<user_id>/ — retirer de l'org
    """
    permission_classes = [IsAuthenticated]

    def _check_permission(self, request, pk):
        user = request.user
        # Spec §6 : promouvoir / changer de rôle / désactiver un membre = Admin d'organisation
        # uniquement (ou Super Admin). Un agent de bureau ne gère plus les membres.
        if is_super_admin(user):
            return True
        return (
            user.organisation_member_id == pk
            and is_org_admin(user)
        )

    def patch(self, request, pk, user_id):
        # Admin d'org / Super Admin gèrent tous les membres ; en plus, un agent de
        # BUREAU de cette org peut modifier un agent de TERRAIN (et seulement lui).
        is_admin_level = self._check_permission(request, pk)
        is_bureau_same_org = is_bureau_agent(request.user) and request.user.organisation_member_id == pk
        if not is_admin_level and not is_bureau_same_org:
            return Response(
                {"error": "Droits insuffisants."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            member = User.objects.get(pk=user_id, organisation_member_id=pk)
        except User.DoesNotExist:
            return Response({"error": "Membre non trouvé dans cette organisation."}, status=status.HTTP_404_NOT_FOUND)

        # Garde-fous agent de bureau : seulement un agent de terrain, et pas de
        # changement de rôle (pas de promotion vers bureau/admin).
        if is_bureau_same_org and not is_admin_level:
            if member.org_role != ORG_ROLE_FIELD:
                return Response(
                    {"error": "Un agent de bureau ne peut modifier qu'un agent de terrain."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            req_role = request.data.get('org_role')
            if req_role and req_role != ORG_ROLE_FIELD:
                return Response(
                    {"error": "Un agent de bureau ne peut pas changer le rôle d'un agent.",
                     "field": "org_role", "errors": {"org_role": "Modification du rôle non autorisée."}},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Modification des informations de l'agent
        email = request.data.get('email')
        if email:
            email = email.strip().lower()
            if User.objects.filter(email=email).exclude(pk=user_id).exists():
                msg = "Cet email est déjà utilisé par un autre utilisateur."
                return Response({"error": msg, "field": "email", "errors": {"email": msg}}, status=status.HTTP_400_BAD_REQUEST)
            member.email = email

        first_name = request.data.get('first_name')
        if first_name is not None:
            member.first_name = first_name.strip()

        last_name = request.data.get('last_name')
        if last_name is not None:
            member.last_name = last_name.strip()

        phone = request.data.get('phone')
        if phone is not None:
            phone = phone.strip()
            # Si c'est un agent de terrain, s'assurer que le téléphone est unique parmi les agents de terrain
            if phone and User.objects.filter(phone=phone, org_role=ORG_ROLE_FIELD).exclude(pk=user_id).exists():
                msg = "Un agent de terrain avec ce numéro de téléphone existe déjà."
                return Response({"error": msg, "field": "phone", "errors": {"phone": msg}}, status=status.HTTP_400_BAD_REQUEST)
            member.phone = phone

        new_role = request.data.get('org_role')
        if new_role:
            if new_role not in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD]:
                return Response({"error": "Rôle invalide.", "field": "org_role", "errors": {"org_role": "Rôle invalide."}}, status=status.HTTP_400_BAD_REQUEST)
            # Règle anti-verrouillage : on ne peut pas rétrograder le DERNIER admin actif de l'org.
            # Le Super Admin peut l'outrepasser (gestion plateforme).
            if (
                not is_super_admin(request.user)
                and member.org_role == ORG_ROLE_ADMIN
                and new_role != ORG_ROLE_ADMIN
                and member.is_active
                and _active_admin_count(member.organisation_member, exclude_user_id=member.pk) == 0
            ):
                return Response(
                    {"error": "Impossible de rétrograder le dernier administrateur actif de l'organisation. "
                              "Promouvez d'abord un autre membre en administrateur."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            member.org_role = new_role
            # Générer code agent si nouveau rôle terrain
            if new_role == ORG_ROLE_FIELD and not member.agent_code:
                member.generate_agent_code()

        member.save()

        serializer = OrganisationMemberSerializer(member)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, user_id):
        # Admin d'org / Super Admin gèrent tous les membres ; en plus, un agent de
        # BUREAU de cette org peut supprimer un agent de TERRAIN (et uniquement lui).
        is_admin_level = self._check_permission(request, pk)
        is_bureau_same_org = is_bureau_agent(request.user) and request.user.organisation_member_id == pk
        if not is_admin_level and not is_bureau_same_org:
            return Response(
                {"error": "Droits insuffisants."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            member = User.objects.get(pk=user_id, organisation_member_id=pk)
        except User.DoesNotExist:
            return Response({"error": "Membre non trouvé dans cette organisation."}, status=status.HTTP_404_NOT_FOUND)

        # Un agent de bureau ne peut supprimer qu'un agent de TERRAIN (jamais un
        # admin ni un autre agent de bureau).
        if is_bureau_same_org and not is_admin_level and member.org_role != ORG_ROLE_FIELD:
            return Response(
                {"error": "Un agent de bureau ne peut supprimer qu'un agent de terrain."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Règle anti-verrouillage : on ne peut pas retirer le DERNIER admin actif de l'org.
        # Le Super Admin peut l'outrepasser (gestion plateforme : il pourra ré-affecter un admin).
        if (
            not is_super_admin(request.user)
            and member.org_role == ORG_ROLE_ADMIN
            and member.is_active
            and _active_admin_count(member.organisation_member, exclude_user_id=member.pk) == 0
        ):
            return Response(
                {"error": "Impossible de retirer le dernier administrateur actif de l'organisation. "
                          "Promouvez d'abord un autre membre en administrateur."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Supprimer physiquement l'agent
        member.delete()

        return Response({"message": "Agent supprimé avec succès de l'organisation."}, status=status.HTTP_200_OK)


ORG_ROLE_LABELS = {
    ORG_ROLE_ADMIN: "Administrateur d'organisation",
    ORG_ROLE_BUREAU: "Agent de bureau",
    ORG_ROLE_FIELD: "Agent de terrain",
}


@extend_schema_view(post=extend_schema(
    tags=['Organisations & Membres'],
    operation_id='organisations_staff_create',
    summary="Créer un compte staff (admin / agent de bureau)",
    description=(
        "Crée un utilisateur staff (`org_admin` ou `bureau_agent`) pour l'organisation : "
        "génère un mot de passe temporaire (envoyé par email, NON renvoyé dans la "
        "réponse) avec le rôle et l'organisation. Authentification requise ; réservé au "
        "Super Admin (is_staff) ou à l'Admin de CETTE organisation. Le frontend force le "
        "changement de mot de passe à la première connexion (`must_change_password`)."
    ),
    parameters=[OpenApiParameter('pk', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'organisation.")],
    request=inline_serializer(
        name='StaffAccountCreateRequest',
        fields={
            'first_name': serializers.CharField(),
            'last_name': serializers.CharField(),
            'email': serializers.EmailField(),
            'org_role': serializers.ChoiceField(choices=[ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]),
            'phone': serializers.CharField(required=False),
            'address': serializers.CharField(required=False),
        },
    ),
    examples=[
        OpenApiExample(
            'Création agent de bureau',
            value={
                'first_name': 'Moussa', 'last_name': 'Traoré',
                'email': 'moussa.traore@example.com', 'org_role': 'bureau_agent',
                'phone': '+221770000000',
            },
            request_only=True,
        ),
    ],
    responses={
        201: OpenApiResponse(
            response=OrganisationMemberSerializer,
            description=(
                "Compte staff créé. La réponse ajoute `must_change_password` (toujours "
                "`true`) et `email_sent` (bool ; `email_error` si l'envoi a échoué). Le "
                "mot de passe temporaire n'est PAS renvoyé (uniquement envoyé par email)."
            ),
        ),
        400: OpenApiResponse(description="Champs requis manquants, org_role invalide, ou email déjà utilisé."),
        401: OpenApiResponse(description="Authentification requise."),
        403: OpenApiResponse(description="Seul un administrateur d'organisation peut créer un compte staff."),
        404: OpenApiResponse(description="Organisation non trouvée."),
    },
))
class StaffAccountCreateView(APIView):
    """POST /organisations/<pk>/staff/create/

    Crée un compte staff (admin/bureau_agent), génère un mot de passe temporaire,
    et envoie un email avec les identifiants.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user

        # Permissions : admin de l'org ou superadmin (un bureau_agent ne crée pas d'admin)
        if not (user.is_staff or (
            user.organisation_member_id == pk
            and user.org_role == ORG_ROLE_ADMIN
        )):
            return Response(
                {"error": "Seul un administrateur d'organisation peut créer un compte staff."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            org = Organisation.objects.get(pk=pk)
        except Organisation.DoesNotExist:
            return Response({"error": "Organisation non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        first_name = (request.data.get('first_name') or '').strip()
        last_name = (request.data.get('last_name') or '').strip()
        email = (request.data.get('email') or '').strip().lower()
        phone = (request.data.get('phone') or '').strip()
        address = (request.data.get('address') or '').strip()
        org_role = (request.data.get('org_role') or '').strip()

        missing = [f for f, v in {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'org_role': org_role,
        }.items() if not v]
        if missing:
            return Response(
                {"error": f"Champs requis manquants : {', '.join(missing)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if org_role not in (ORG_ROLE_ADMIN, ORG_ROLE_BUREAU):
            return Response(
                {"error": "org_role doit être 'org_admin' ou 'bureau_agent'. Pour un agent de terrain, utilisez /organisations/<pk>/agents/create/."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email=email).exists():
            return Response(
                {"error": "Un utilisateur avec cet email existe déjà."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Génération mot de passe temporaire
        temp_password = ''.join(random.choices(
            string.ascii_letters + string.digits + '!@#$%', k=12
        ))

        member = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone or None,
            address=address or None,
            user_type='admin' if org_role == ORG_ROLE_ADMIN else 'citizen',
            org_role=org_role,
            organisation_member=org,
            is_active=True,
            is_verified=True,
        )
        member.set_password(temp_password)
        member.save()

        # Envoi email
        email_sent = False
        email_error = None
        try:
            context = {
                'first_name': member.first_name,
                'last_name': member.last_name,
                'email': member.email,
                'password': temp_password,
                'role_label': ORG_ROLE_LABELS.get(org_role, org_role),
                'organisation_name': org.name,
            }
            send_email.delay(
                subject=f'🌍 Bienvenue sur Map Action — Compte {ORG_ROLE_LABELS.get(org_role, org_role)}',
                template_name='emails/staff_account_email.html',
                context=context,
                to_email=member.email,
            )
            email_sent = True
            logger.info(f"Email staff envoyé (queue Celery) à {member.email} pour user {member.id}")
        except Exception as e:
            email_error = str(e)
            logger.error(f"Erreur envoi email staff à {member.email}: {e}", exc_info=True)

        response_data = OrganisationMemberSerializer(member).data
        response_data.update({
            # Mot de passe temporaire renvoyé une seule fois (comme `initial_pin` pour les
            # agents de terrain) : l'admin peut le communiquer même si l'email n'arrive pas.
            'temp_password': temp_password,
            'email_sent': email_sent,
            'must_change_password': True,
        })
        if email_error:
            response_data['email_error'] = email_error
        return Response(response_data, status=status.HTTP_201_CREATED)


_AGENT_ROLES = [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD]


@extend_schema(
    tags=['Organisations & Membres'],
    operation_id='agents_list',
    summary="Lister les agents (global)",
    description="Tous les agents (membres d'organisation : org_admin, bureau_agent, "
                "field_agent), **plus récents d'abord**, paginés. Filtres : `?search=` "
                "(nom/email/organisation), `?role=org_admin|bureau_agent|field_agent`, "
                "`?status=active|inactive`. Authentification requise.",
    parameters=[
        OpenApiParameter('search', OpenApiTypes.STR, OpenApiParameter.QUERY, description="Nom, email ou organisation."),
        OpenApiParameter('role', OpenApiTypes.STR, OpenApiParameter.QUERY, description="org_admin|bureau_agent|field_agent."),
        OpenApiParameter('status', OpenApiTypes.STR, OpenApiParameter.QUERY, description="active|inactive."),
    ],
    responses={200: OrganisationMemberSerializer(many=True)},
)
class AgentListView(generics.ListAPIView):
    """GET /agents/ — liste globale des agents (membres d'organisation avec rôle)."""
    permission_classes = [IsAuthenticated]
    serializer_class = OrganisationMemberSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        user = self.request.user
        qs = (User.objects
              .filter(org_role__in=_AGENT_ROLES)
              .select_related('organisation_member')
              .order_by('-date_joined'))
        # Portée : le Super Admin voit TOUS les agents ; un admin/membre d'org ne voit
        # que les agents de SON organisation (pas de fuite cross-org).
        if not is_super_admin(user):
            org_id = getattr(user, 'organisation_member_id', None)
            qs = qs.filter(organisation_member_id=org_id) if org_id else qs.none()
        p = self.request.query_params
        search = (p.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search)
                | Q(email__icontains=search) | Q(organisation_member__name__icontains=search)
            )
        role = p.get('role')
        if role:
            qs = qs.filter(org_role=role)
        statut = p.get('status')
        if statut:
            qs = qs.filter(is_active=(str(statut).lower() in ('active', 'actif', 'true', '1')))
        return qs


@extend_schema(
    tags=['Organisations & Membres'],
    operation_id='agents_stats',
    summary="Stats du dashboard agents",
    description="Cartes du dashboard agents : total, actifs, admins, agents de terrain. "
                "Authentification requise.",
    responses={200: inline_serializer(name='AgentStats', fields={
        'total': serializers.IntegerField(),
        'active': serializers.IntegerField(),
        'admins': serializers.IntegerField(),
        'bureau_agents': serializers.IntegerField(),
        'field_agents': serializers.IntegerField(),
    })},
)
class AgentStatsView(APIView):
    """GET /agents/stats/ — compteurs pour les cartes du dashboard agents."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agents = User.objects.filter(org_role__in=_AGENT_ROLES)
        # Même portée que /agents/ : le Super Admin compte tous les agents ; un
        # admin/membre d'org ne compte que ceux de SON organisation.
        if not is_super_admin(request.user):
            org_id = getattr(request.user, 'organisation_member_id', None)
            agents = agents.filter(organisation_member_id=org_id) if org_id else agents.none()
        return Response({
            'total': agents.count(),
            'active': agents.filter(is_active=True).count(),
            'admins': agents.filter(org_role=ORG_ROLE_ADMIN).count(),
            'bureau_agents': agents.filter(org_role=ORG_ROLE_BUREAU).count(),
            'field_agents': agents.filter(org_role=ORG_ROLE_FIELD).count(),
        })
