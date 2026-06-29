"""Organisation & tenant-config endpoints + member management."""
import string
import random
import logging

from Mapapi.views.common import CustomPageNumberPagination
from django.db.models import Count

logger = logging.getLogger(__name__)

from rest_framework import status, generics, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from ..models import Organisation, User, Incident, ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD
from ..serializer import OrganisationSerializer, OrganisationMemberSerializer
from ..Send_mails import send_email
from .user import send_sms


class OrganisationViewSet(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = Organisation.objects.all()
    serializer_class = OrganisationSerializer
    permission_classes = []
    pagination_class = CustomPageNumberPagination  # Liste d'orgs sans pagination (généralement peu d'orgs)

    def get_queryset(self):
        return Organisation.objects.all()


@extend_schema(
    description="Détail enrichi d'une organisation avec statistiques (membres, incidents, etc.).",
    responses={200: OrganisationSerializer},
)
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


@extend_schema(
    description="Liste les membres d'une organisation. Réservé aux admins et agents de bureau de l'org.",
    responses={200: OrganisationMemberSerializer(many=True)},
)
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
        if not (user.is_staff or user.is_superuser or (
            user.organisation_member_id == org_id
            and user.org_role in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]
        )):
            return Response(
                {"error": "Vous n'avez pas les droits pour voir les membres de cette organisation."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().list(request, *args, **kwargs)


@extend_schema(
    description="Ajouter un membre à une organisation. Génère un agent_code si le rôle est field_agent.",
    request=OrganisationMemberSerializer,
    responses={201: OrganisationMemberSerializer},
)
class OrganisationMemberCreateView(APIView):
    """POST /organisations/<pk>/members/ — ajouter un membre."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        # Seul un admin org ou agent de bureau de cette org peut ajouter
        if not (user.is_staff or user.is_superuser or (
            user.organisation_member_id == pk
            and user.org_role in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]
        )):
            return Response(
                {"error": "Vous n'avez pas les droits pour gérer les membres."},
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


@extend_schema(
    description=(
        "Endpoint tout-en-un : crée un utilisateur ET l'affecte comme agent de terrain "
        "dans l'organisation. Génère agent_code + PIN initial + envoie email automatiquement."
    ),
    request={
        'application/json': {
            'type': 'object',
            'required': ['first_name', 'last_name', 'email', 'phone'],
            'properties': {
                'first_name': {'type': 'string'},
                'last_name': {'type': 'string'},
                'email': {'type': 'string', 'format': 'email'},
                'phone': {'type': 'string', 'example': '+221771234567'},
                'address': {'type': 'string'},
            },
        }
    },
    responses={201: OrganisationMemberSerializer},
)
class FieldAgentCreateView(APIView):
    """POST /organisations/<pk>/agents/create/

    Endpoint tout-en-un destiné aux admins d'organisation :
    crée l'utilisateur, l'affecte comme agent de terrain, génère
    agent_code + PIN initial, et envoie l'email d'identifiants.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user

        # Permissions : org_admin/bureau_agent de cette org ou superadmin
        if not (user.is_staff or user.is_superuser or (
            user.organisation_member_id == pk
            and user.org_role in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]
        )):
            return Response(
                {"error": "Vous n'avez pas les droits pour créer un agent dans cette organisation."},
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
            return Response(
                {"error": f"Champs requis manquants : {', '.join(missing)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Email unique
        if User.objects.filter(email=email).exists():
            return Response(
                {"error": "Un utilisateur avec cet email existe déjà. Utilise l'endpoint /members/add/ pour l'affecter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Téléphone unique parmi les agents de terrain (sinon login PIN ambigu)
        if User.objects.filter(phone=phone, org_role=ORG_ROLE_FIELD).exists():
            return Response(
                {"error": "Un agent de terrain avec ce numéro de téléphone existe déjà."},
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

        # Envoi du SMS avec le PIN
        sms_sent = False
        try:
            sms_message = f"Bienvenue sur Map Action. Votre code PIN de connexion est : {initial_pin}"
            sms_sent = send_sms(member.phone, sms_message)
            if sms_sent:
                logger.info(f"SMS PIN envoyé à {member.phone} pour l'agent {member.id}")
            else:
                logger.error(f"Echec envoi SMS PIN à {member.phone} pour l'agent {member.id}")
        except Exception as e:
            logger.error(f"Erreur exception envoi SMS PIN à {member.phone}: {e}", exc_info=True)

        serializer = OrganisationMemberSerializer(member)
        response_data = serializer.data
        response_data.update({
            'initial_pin': initial_pin,
            'must_change_pin': member.must_change_pin,
            'email_sent': email_sent,
            'sms_sent': sms_sent,
        })
        if email_error:
            response_data['email_error'] = email_error
        return Response(response_data, status=status.HTTP_201_CREATED)


@extend_schema(
    description="Modifier le rôle ou retirer un membre d'une organisation.",
    responses={200: OrganisationMemberSerializer},
)
class OrganisationMemberDetailView(APIView):
    """
    PATCH  /organisations/<pk>/members/<user_id>/ — modifier le rôle
    DELETE /organisations/<pk>/members/<user_id>/ — retirer de l'org
    """
    permission_classes = [IsAuthenticated]

    def _check_permission(self, request, pk):
        user = request.user
        if user.is_staff or user.is_superuser:
            return True
        return (
            user.organisation_member_id == pk
            and user.org_role in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]
        )

    def patch(self, request, pk, user_id):
        if not self._check_permission(request, pk):
            return Response(
                {"error": "Droits insuffisants."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            member = User.objects.get(pk=user_id, organisation_member_id=pk)
        except User.DoesNotExist:
            return Response({"error": "Membre non trouvé dans cette organisation."}, status=status.HTTP_404_NOT_FOUND)

        # Modification des informations de l'agent
        email = request.data.get('email')
        if email:
            email = email.strip().lower()
            if User.objects.filter(email=email).exclude(pk=user_id).exists():
                return Response({"error": "Cet email est déjà utilisé par un autre utilisateur."}, status=status.HTTP_400_BAD_REQUEST)
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
                return Response({"error": "Un agent de terrain avec ce numéro de téléphone existe déjà."}, status=status.HTTP_400_BAD_REQUEST)
            member.phone = phone

        new_role = request.data.get('org_role')
        if new_role:
            if new_role not in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD]:
                return Response({"error": "Rôle invalide."}, status=status.HTTP_400_BAD_REQUEST)
            member.org_role = new_role
            # Générer code agent si nouveau rôle terrain
            if new_role == ORG_ROLE_FIELD and not member.agent_code:
                member.generate_agent_code()

        member.save()

        serializer = OrganisationMemberSerializer(member)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, user_id):
        if not self._check_permission(request, pk):
            return Response(
                {"error": "Droits insuffisants."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            member = User.objects.get(pk=user_id, organisation_member_id=pk)
        except User.DoesNotExist:
            return Response({"error": "Membre non trouvé dans cette organisation."}, status=status.HTTP_404_NOT_FOUND)

        # Supprimer physiquement l'agent
        member.delete()

        return Response({"message": "Agent supprimé avec succès de l'organisation."}, status=status.HTTP_200_OK)


ORG_ROLE_LABELS = {
    ORG_ROLE_ADMIN: "Administrateur d'organisation",
    ORG_ROLE_BUREAU: "Agent de bureau",
    ORG_ROLE_FIELD: "Agent de terrain",
}


@extend_schema(
    description=(
        "Crée un utilisateur staff (admin ou agent de bureau) pour l'organisation. "
        "Génère un mot de passe temporaire et envoie un email avec les identifiants, "
        "le rôle et l'organisation. Le frontend force le changement de mot de passe à "
        "la première connexion."
    ),
    request={
        'application/json': {
            'type': 'object',
            'required': ['first_name', 'last_name', 'email', 'org_role'],
            'properties': {
                'first_name': {'type': 'string'},
                'last_name': {'type': 'string'},
                'email': {'type': 'string', 'format': 'email'},
                'phone': {'type': 'string'},
                'address': {'type': 'string'},
                'org_role': {'type': 'string', 'enum': [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]},
            },
        }
    },
    responses={201: OrganisationMemberSerializer},
)
class StaffAccountCreateView(APIView):
    """POST /organisations/<pk>/staff/create/

    Crée un compte staff (admin/bureau_agent), génère un mot de passe temporaire,
    et envoie un email avec les identifiants.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user

        # Permissions : admin de l'org ou superadmin (un bureau_agent ne crée pas d'admin)
        if not (user.is_staff or user.is_superuser or (
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
            'email_sent': email_sent,
            'must_change_password': True,
        })
        if email_error:
            response_data['email_error'] = email_error
        return Response(response_data, status=status.HTTP_201_CREATED)
