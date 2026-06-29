"""Incident endpoints: CRUD, filters, search, reporting windows (monthly/weekly), handling actions."""
import subprocess
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from ..serializer import *
from ..models import (
    Collaboration, COLLAB_ROLE_LEADER, COLLAB_ROLE_CONTRIBUTOR, COLLAB_ROLE_OBSERVER,
    RESOLVED, TAKEN, TASK_DONE, TASK_FAILED,
    ORG_ROLE_FIELD, ORG_ROLE_ADMIN, ORG_ROLE_BUREAU,
    Prediction, PredictionStatus,
    ChatHistory, CHAT_ROLE_USER, CHAT_ROLE_ASSISTANT,
)
from ..permissions import IsIncidentLeader, IsSuperAdminOrOrgOwnIncident, IsSuperAdmin
from ..tasks import analyze_incident_with_model_task
from ..Send_mails import send_email
import logging

User = get_user_model()

logger = logging.getLogger(__name__)
from ..services.model_chat_client import ask_model_chat
from .common import CustomPageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import check_password


@extend_schema(
    description="Endpoint allowing retrieval of incident by zone.",
    request=IncidentSerializer,
    responses={200: IncidentSerializer, 404: "Incident not found"},  
)
class IncidentByZoneAPIView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer
    
    def get(self, request, format=None, **kwargs):
        try:
            zone = kwargs['zone']
            item = Incident.objects.filter(zone=zone).select_related('user_id', 'category_id').order_by('-pk')
            serializer = IncidentGetSerializer(item, many=True)
            return Response(serializer.data)
        except Incident.DoesNotExist:
            return Response(status=404)

@extend_schema(
    description="Endpoint allowing retrieval, updating, and deletion of an incident.",
    request=IncidentSerializer,
    responses={200: IncidentSerializer, 404: "Incident not found"},  
)
class IncidentAPIView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get(self, request, id, format=None):
        try:
            item = Incident.objects.get(pk=id)
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
        item.save(update_fields=['is_deleted'])
        return Response(status=204)

@extend_schema(
    description="Endpoint for creating and retrieve a new incident."
        "Users can submit details of an incident by providing the required information via a POST request."
        "The submitted data will be validated and stored in the system."
        "Upon success, a status code 201 (Created) will be returned along with details of the newly created incident."
        "In case of validation errors or issues with creating the incident, a status code 400 (Bad Request) will be returned along with information about the encountered errors."
        "Users must ensure that the provided data adheres to the format and constraints defined for incidents in the system.",
    request=IncidentSerializer,  
    responses={201: IncidentSerializer, 400: "Bad Request"},  
)
class IncidentAPIListView(generics.CreateAPIView):
    permission_classes = ()
    
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer
    
    def get(self, request, format=None):
        items = Incident.objects.select_related('user_id', 'category_id').order_by('-pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = IncidentGetSerializer(result_page, many=True)
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


@extend_schema(
    description="Endpoint allowing retrieval of incidents reported by the authenticated user.",
    responses={200: IncidentGetSerializer(many=True)},
)
class MyIncidentsView(generics.ListAPIView):
    """GET /my-incidents/ — incidents reportés par l'utilisateur connecté."""
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentGetSerializer

    def get_queryset(self):
        return (
            Incident.objects
            .filter(user_id=self.request.user)
            .select_related('user_id', 'category_id')
            .order_by('-created_at')
        )


@extend_schema(
    description="Notifications (dérivées, sans modèle) de l'état des incidents du citoyen connecté. "
                "Renvoie les incidents passés à 'taken_into_account' ou 'resolved'. "
                "Le suivi lu/non-lu est géré côté application mobile.",
    responses={200: dict},
)
class MyIncidentNotificationsView(APIView):
    """GET /my-incidents/notifications/

    Endpoint léger destiné à l'app mobile du citoyen : il liste l'état actuel
    des incidents qu'il a déclarés et qui ont avancé (pris en compte ou résolu).
    Aucun modèle de notification n'est utilisé ; la liste est calculée à la volée.
    """
    permission_classes = [IsAuthenticated]

    _MESSAGES = {
        TAKEN: "Votre incident « {title} » a été pris en compte.",
        RESOLVED: "Votre incident « {title} » a été résolu.",
    }

    def get(self, request, *args, **kwargs):
        incidents = (
            Incident.objects
            .filter(user_id=request.user, etat__in=[TAKEN, RESOLVED])
            .only('id', 'title', 'zone', 'etat', 'created_at', 'resolution_end_date')
            .order_by('-created_at')
        )

        notifications = []
        for inc in incidents:
            title = inc.title or inc.zone or f"#{inc.id}"
            notifications.append({
                "incident_id": inc.id,
                "title": inc.title,
                "zone": inc.zone,
                "etat": inc.etat,
                "message": self._MESSAGES[inc.etat].format(title=title),
                "resolution_end_date": inc.resolution_end_date,
                "created_at": inc.created_at,
            })

        return Response({
            "count": len(notifications),
            "results": notifications,
        }, status=status.HTTP_200_OK)


@extend_schema(
    description="Incidents de l'organisation. Filtre ?source=agents|citizens|all (défaut: all).",
    responses={200: IncidentGetSerializer(many=True)},
)
class OrgIncidentsView(generics.ListAPIView):
    """GET /org-incidents/ — incidents liés à l'organisation de l'utilisateur.

    ?source=agents  → incidents reportés par les agents de terrain de l'org
    ?source=citizens → incidents reportés par les citoyens (tous les autres)
    ?source=all (défaut) → tous
    """
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentGetSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Incident.objects.all().select_related('user_id', 'category_id').order_by('-created_at')

        org = user.organisation_member

        if not org:
            return Incident.objects.none()

        source = self.request.query_params.get('source', 'all')
        mode = self.request.query_params.get('mode', None)
        # IDs des agents de terrain de CETTE org
        agent_ids = org.members.filter(org_role=ORG_ROLE_FIELD).values_list('id', flat=True)

        qs = Incident.objects.select_related('user_id', 'category_id')

        org_members = org.members.all()

        # IDs des agents de terrain de TOUTES les organisations
        all_field_agent_ids = User.objects.filter(org_role=ORG_ROLE_FIELD).values_list('id', flat=True)
        # Agents de terrain des AUTRES organisations
        other_field_agent_ids = all_field_agent_ids.exclude(id__in=agent_ids)

        if source == 'agents_or_internal':
            # Option B: Logique OU (Incidents créés par les agents de l'org OU pris en interne par l'org)
            qs = qs.filter(
                Q(user_id__in=agent_ids) |
                Q(take_in_charge_mode__iexact='internal', taken_by__in=org_members)
            )
            # Désactiver le filtre mode strict car il casserait l'union "OU"
            mode = None 
        elif source == 'agents':
            qs = qs.filter(user_id__in=agent_ids)
        elif source == 'citizens':
            qs = qs.exclude(user_id__in=agent_ids)
        # source == 'all' : pas de filtre supplémentaire

        # Règle de sécurité globale : on masque les incidents 'internal' qui appartiennent à D'AUTRES organisations
        qs = qs.filter(
            Q(take_in_charge_mode__isnull=True) |
            ~Q(take_in_charge_mode__iexact='internal') |
            Q(take_in_charge_mode__iexact='internal', taken_by__in=org_members)
        )

        # Règle de sécurité globale : on masque les incidents déclarés par les agents de terrain
        # d'AUTRES organisations (sauf si pris en charge par cette org).
        qs = qs.exclude(
            Q(user_id__in=other_field_agent_ids) & ~Q(taken_by__in=org_members)
        )

        # Si le front-end demande explicitement un filtre mode additionnel (uniquement si ce n'est pas l'Option B)
        if mode == 'internal':
            qs = qs.filter(take_in_charge_mode__iexact='internal', taken_by__in=org_members)
        elif mode:
            qs = qs.filter(take_in_charge_mode__iexact=mode)
            
        return qs.order_by('-created_at')


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

        if not self._can_manage_assignment(request.user, incident):
            return Response({"error": "Droits insuffisants."}, status=status.HTTP_403_FORBIDDEN)

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
        if user.org_role not in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]:
            return False
        if not user.organisation_member:
            return False
        if incident.user_id and incident.user_id.organisation_member == user.organisation_member:
            return True
        if incident.taken_by and incident.taken_by.organisation_member == user.organisation_member:
            return True
        return False


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


class AgentAssignedIncidentsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentAssignmentSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return IncidentAssignment.objects.all().select_related('incident', 'agent', 'assigned_by')
        if user.org_role != ORG_ROLE_FIELD:
            return IncidentAssignment.objects.none()
        return IncidentAssignment.objects.filter(agent=user).select_related('incident', 'agent', 'assigned_by')


class FieldReportListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FieldReportSerializer

    def get_queryset(self):
        user = self.request.user
        qs = FieldReport.objects.select_related(
            'incident', 'agent', 'agent__organisation_member'
        ).order_by('-visited_at')

        # Super admin / staff : accès total
        if user.is_superuser or user.is_staff:
            pass
        elif user.org_role == ORG_ROLE_FIELD:
            # Agent de terrain : ses propres rapports uniquement
            qs = qs.filter(agent=user)
        elif user.organisation_member and user.org_role in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]:
            # Agent de bureau / admin d'organisation
            incident_id = self.request.query_params.get('incident') or self.request.query_params.get('incident_id')
            if incident_id:
                try:
                    incident = Incident.objects.get(pk=incident_id)
                    # L'org a-t-elle un lien avec l'incident ?
                    is_owner = incident.user_id and incident.user_id.organisation_member == user.organisation_member
                    is_taker = incident.taken_by and incident.taken_by.organisation_member == user.organisation_member
                    has_collab = Collaboration.objects.filter(
                        incident=incident,
                        user__organisation_member=user.organisation_member,
                        status='accepted'
                    ).exists()
                    
                    if is_owner or is_taker or has_collab:
                        qs = qs.filter(incident=incident)
                    else:
                        return FieldReport.objects.none()
                except (Incident.DoesNotExist, ValueError):
                    return FieldReport.objects.none()
            else:
                # Liste générale : rapports des agents de son org ou sur des incidents liés à son org
                qs = qs.filter(
                    Q(agent__organisation_member=user.organisation_member) |
                    Q(incident__user_id__organisation_member=user.organisation_member) |
                    Q(incident__taken_by__organisation_member=user.organisation_member) |
                    Q(incident__collaboration__user__organisation_member=user.organisation_member, incident__collaboration__status='accepted')
                ).distinct()
        else:
            return FieldReport.objects.none()

        # Filtre optionnel par incident (appliqué à tous les rôles restants qui ont pu passer)
        incident_id = self.request.query_params.get('incident') or self.request.query_params.get('incident_id')
        if incident_id and (user.is_superuser or user.is_staff or user.org_role == ORG_ROLE_FIELD):
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


@extend_schema(
    description="Connexion d'un agent de terrain via son code agent.",
    request={'application/json': {'type': 'object', 'properties': {'agent_code': {'type': 'string'}}}},
    responses={200: 'Tokens JWT'},
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


@extend_schema(
    description="Basculer la visibilité publique d'un incident (is_public).",
    responses={200: IncidentSerializer},
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
        elif not (user.is_staff or user.is_superuser):
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


@extend_schema(
    description="Incidents résolus avec détails enrichis : prédiction, organisations impliquées, tâches groupées par organisation. "
                "Le superadmin voit tout ; les autres voient uniquement les incidents liés à leur organisation.",
    responses={200: IncidentResolvedSerializer(many=True)},
)
class IncidentResolvedAPIListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentResolvedSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        user = self.request.user
        qs = Incident.objects.filter(etat=RESOLVED)

        # Isolation par organisation. Le super admin voit tout.
        if not user.is_superuser:
            org = user.organisation_member
            # Agents de terrain de TOUTES les organisations
            all_field_agent_ids = User.objects.filter(org_role=ORG_ROLE_FIELD).values_list('id', flat=True)
            # Incidents citoyens : déclarés par un user qui n'est agent de terrain d'aucune org
            citizen_q = ~Q(user_id__in=all_field_agent_ids)

            if org:
                agent_ids = org.members.filter(org_role=ORG_ROLE_FIELD).values_list('id', flat=True)
                org_members = org.members.all()
                # ses agents + citoyens + incidents pris en charge par l'org
                qs = qs.filter(
                    Q(user_id__in=agent_ids) | citizen_q | Q(taken_by__in=org_members)
                )
                # masque les incidents 'internal' appartenant à d'autres orgs
                qs = qs.filter(
                    Q(take_in_charge_mode__isnull=True) |
                    ~Q(take_in_charge_mode__iexact='internal') |
                    Q(take_in_charge_mode__iexact='internal', taken_by__in=org_members)
                )
            else:
                # Utilisateur sans organisation : uniquement les incidents citoyens (publics)
                qs = qs.filter(citizen_q)

        # Optimisation des requêtes pour le serializer enrichi
        return qs.select_related(
            'user_id', 'category_id', 'taken_by__organisation_member'
        ).prefetch_related(
            'collaboration_set__user__organisation_member',
            'tasks__created_by__organisation_member',
            'tasks__assigned_to',
        ).order_by('-created_at')

@extend_schema(
    description="Endpoint allowing filtering retrieval incidents",
    request=IncidentSerializer,
    responses={200: IncidentSerializer, 404: "incident not found"},  
)
class IncidentFilterView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        filter_type = request.query_params.get('filter_type')
        custom_start = request.query_params.get('custom_start')
        custom_end = request.query_params.get('custom_end')

        incidents = Incident.objects.all()

        # Isolation par organisation. Le super admin voit tout.
        user = request.user
        if not user.is_superuser:
            org = user.organisation_member
            # Agents de terrain de TOUTES les organisations
            all_field_agent_ids = User.objects.filter(org_role=ORG_ROLE_FIELD).values_list('id', flat=True)
            # Incidents citoyens : déclarés par un user qui n'est agent de terrain d'aucune org
            citizen_q = ~Q(user_id__in=all_field_agent_ids)

            if org:
                agent_ids = org.members.filter(org_role=ORG_ROLE_FIELD).values_list('id', flat=True)
                org_members = org.members.all()
                # ses agents + citoyens + incidents pris en charge par l'org
                incidents = incidents.filter(
                    Q(user_id__in=agent_ids) | citizen_q | Q(taken_by__in=org_members)
                )
                # masque les incidents 'internal' appartenant à d'autres orgs
                incidents = incidents.filter(
                    Q(take_in_charge_mode__isnull=True) |
                    ~Q(take_in_charge_mode__iexact='internal') |
                    Q(take_in_charge_mode__iexact='internal', taken_by__in=org_members)
                )
            else:
                # Utilisateur sans organisation : uniquement les incidents citoyens (publics)
                incidents = incidents.filter(citizen_q)

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

        # Serializer léger pour la carte : aucun champ relationnel imbriqué -> 1 seule requête
        incidents = incidents.only(
            'id', 'title', 'zone', 'lattitude', 'longitude',
            'etat', 'category_id', 'created_at', 'progress', 'take_in_charge_mode',
        )
        serializer = IncidentMapSerializer(incidents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

@extend_schema(
    description="Endpoint allowing retrieval an incident not resolved.",
    request=IncidentSerializer,
    responses={200: IncidentSerializer, 404: "Incident not found"},  
)
class IncidentNotResolvedAPIListView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get(self, request, format=None):
        items = Incident.objects.filter(etat="declared").select_related('user_id', 'category_id').order_by('pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = IncidentGetSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

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


@extend_schema(
    description="Endpoint allowing retrieval of incident by month on zone.",
    request=IncidentSerializer,
    responses={200: IncidentSerializer, 404: "Incident not found"},  
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

@extend_schema(
    description="Endpoint allowing retrieval of incident on week.",
    request=IncidentSerializer,
    responses={200: IncidentSerializer, 404: "Incident not found"},  
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

@extend_schema(
    description="Endpoint allowing retrieval of incident on week by zone.",
    request=IncidentSerializer,
    responses={200: IncidentSerializer, 404: "Incident not found"},  
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

@extend_schema(
    description="Endpoint allowing retrieval, updating, and deletion of a category.",
    request=CategorySerializer,
    responses={200: CategorySerializer, 404: "category not found"},  
)

@extend_schema(
    description="Endpoint for search incidents",
    responses={200: IncidentSerializer(many=True)},
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

@extend_schema(
    description="Endpoint to change incident status",
    responses={200: UserActionSerializer()},
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
            action_message = f"took incident {incident_id} into account"
        elif action == "resolved":
            incident.etat = "resolved"
            action_message = f"resolved incident {incident_id}"

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

@extend_schema(
    description="Endpoint to get user who took incident into account",
    responses={200: UserSerializer()},
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


@extend_schema(
    description=(
        "Prise en charge d'un incident.\n\n"
        "Body JSON :\n"
        "- mode = 'internal' : prise en charge interne (visible uniquement par les membres de l'organisation).\n"
        "- mode = 'collaborative' : prise en charge collaborative ouverte aux autres organisations. "
        "Doit alors préciser role = 'leader' | 'contributor' | 'observer'.\n\n"
        "Règles :\n"
        "- observer est auto-accepté.\n"
        "- contributor est auto-accepté tant qu'aucun leader n'est désigné ; sinon il passe en pending.\n"
        "- leader définit incident.taken_by et remet les contributors déjà acceptés en pending pour validation."
    ),
    responses={200: IncidentSerializer},
)
class TakeInChargeView(APIView):
    """POST /incidents/<incident_id>/take_in_charge/"""
    permission_classes = [IsAuthenticated]

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
            incident.save(update_fields=['taken_by', 'etat', 'take_in_charge_mode'])

            collaboration, created = Collaboration.objects.get_or_create(
                incident=incident,
                user=request.user,
                defaults={'role': COLLAB_ROLE_LEADER, 'status': 'accepted'},
            )
            if not created:
                collaboration.role = COLLAB_ROLE_LEADER
                collaboration.status = 'accepted'
                collaboration.save(update_fields=['role', 'status'])

            action_message = f"took incident {incident_id} into account in internal mode"
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
            if incident.etat == 'declared':
                incident.etat = 'taken_into_account'
            incident.take_in_charge_mode = 'collaborative'
            incident.save(update_fields=['taken_by', 'etat', 'take_in_charge_mode'])

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

            action_message = f"took incident {incident_id} into account as leader (collaborative)"
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

        action_message = f"joined incident {incident_id} as {role} ({collab_status})"
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


@extend_schema(
    description="Clôturer un incident. Requiert resolution_start_date et resolution_end_date. "
                "Toutes les tâches doivent être terminées (done ou failed).",
    responses={200: IncidentSerializer},
)
class CloseIncidentView(APIView):
    """POST /incidents/<incident_id>/close/"""
    permission_classes = [IsAuthenticated, IsIncidentLeader]

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
                incident.save(update_fields=['is_deleted'])
            deleted_ids.append(incident_id)

        return Response({
            "deleted_ids": deleted_ids,
            "unauthorized_ids": unauthorized_ids,
            "not_found_ids": not_found_ids,
            "message": f"{len(deleted_ids)} incident(s) supprimé(s)."
        }, status=status.HTTP_200_OK)


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


@extend_schema(
    description="Lister les incidents supprimés (corbeille). Super Admin uniquement.",
    responses={200: IncidentGetSerializer(many=True)},
)
class TrashIncidentsView(generics.ListAPIView):
    """GET /incidents/trash/ — liste des incidents supprimés (is_deleted=True)."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = IncidentGetSerializer

    def get_queryset(self):
        return Incident.objects.filter(is_deleted=True).select_related('user_id', 'category_id').order_by('-created_at')


@extend_schema(
    description="Restaurer un incident supprimé (corbeille). Super Admin uniquement.",
    responses={200: IncidentGetSerializer},
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


@extend_schema(
    description="Récupérer l'analyse AI (Prediction) d'un incident.",
    responses={200: PredictionSerializer, 404: "Pas de prédiction"},
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


@extend_schema(
    description="Relancer l'analyse AI d'un incident (Super Admin uniquement).",
    responses={202: PredictionSerializer, 404: "Incident non trouvé"},
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


@extend_schema(
    description=(
        "Chat LLM par incident. GET: récupère l'historique. "
        "POST: envoie une question, le serveur appelle le model-deploy /chat "
        "avec le contexte de la Prediction et stocke les deux messages (user, assistant)."
    ),
)
class IncidentChatView(APIView):
    """GET/POST /MapApi/incidents/<incident_id>/chat/."""
    permission_classes = [IsAuthenticated]

    def get(self, request, incident_id):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist:
            return Response({"error": "Incident non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        history = (
            incident.chat_messages
            .filter(role__in=[CHAT_ROLE_USER, CHAT_ROLE_ASSISTANT])
            .order_by('created_at', 'id')
        )
        return Response(
            {
                "history": [
                    {
                        "role": m.role,
                        "content": m.content,
                        "created_at": m.created_at,
                        "user_id": m.user_id,
                    }
                    for m in history
                ]
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

        # Build the conversation payload from the persisted history.
        history_qs = incident.chat_messages.filter(
            role__in=[CHAT_ROLE_USER, CHAT_ROLE_ASSISTANT]
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
            user=None,  # assistant message has no user
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


@extend_schema(
    description="Connexion d'un agent de terrain via téléphone + PIN 4 chiffres.",
    request={'application/json': {'type': 'object', 'properties': {'phone': {'type': 'string'}, 'pin': {'type': 'string'}}}},
    responses={200: 'Tokens JWT + must_change_pin flag'},
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


@extend_schema(
    description="Changer le PIN de l'agent connecté. Requiert l'ancien PIN.",
    request={'application/json': {'type': 'object', 'properties': {'old_pin': {'type': 'string'}, 'new_pin': {'type': 'string'}}}},
    responses={200: 'PIN changé avec succès'},
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


class GlobalImpactAPIView(APIView):
    """
    GET /impact/global/
    Retourne les statistiques d'impact global basées sur les incidents valides et leurs prédictions.
    Supporte les filtres : ?period=30d|90d|year & scope=resolved|ongoing & category=text & search=text
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from ..services.impact_service import ImpactCalculatorService

        service = ImpactCalculatorService(user=request.user, query_params=request.query_params)
        data = service.compute()

        return Response(data, status=status.HTTP_200_OK)
