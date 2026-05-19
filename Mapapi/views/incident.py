"""Incident endpoints: CRUD, filters, search, reporting windows (monthly/weekly), handling actions."""
import subprocess
from datetime import timedelta

from django.conf import settings
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
    Collaboration, COLLAB_ROLE_LEADER, RESOLVED, TASK_DONE, TASK_FAILED,
    ORG_ROLE_FIELD, ORG_ROLE_ADMIN, ORG_ROLE_BUREAU,
)
from ..permissions import IsIncidentLeader, IsSuperAdminOrOrgOwnIncident, IsSuperAdmin
from .common import CustomPageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken


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
        org = user.organisation_member

        if not org:
            return Incident.objects.none()

        source = self.request.query_params.get('source', 'all')
        # IDs des agents de terrain de l'org
        agent_ids = org.members.filter(org_role=ORG_ROLE_FIELD).values_list('id', flat=True)

        qs = Incident.objects.select_related('user_id', 'category_id')

        if source == 'agents':
            qs = qs.filter(user_id__in=agent_ids)
        elif source == 'citizens':
            qs = qs.exclude(user_id__in=agent_ids)
        # source == 'all' : pas de filtre supplémentaire

        return qs.order_by('-created_at')


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


@extend_schema(
    description="Endpoint allowing retrieval an incident resolved.",
    request=IncidentSerializer,
    responses={200: IncidentSerializer, 404: "Incident not found"},  
)
class IncidentResolvedAPIListView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get(self, request, format=None):
        items = Incident.objects.filter(etat="resolved").select_related('user_id', 'category_id').order_by('pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = IncidentGetSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

@extend_schema(
    description="Endpoint allowing filtering retrieval incidents",
    request=IncidentSerializer,
    responses={200: IncidentSerializer, 404: "incident not found"},  
)
class IncidentFilterView(APIView):
    def get(self, request, *args, **kwargs):
        filter_type = request.query_params.get('filter_type')
        custom_start = request.query_params.get('custom_start')
        custom_end = request.query_params.get('custom_end')

        incidents = Incident.objects.all()

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

        serializer = IncidentSerializer(incidents, many=True)
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
    description="Prise en charge d'un incident par une organisation. "
                "L'utilisateur devient leader et une Collaboration 'leader/accepted' est créée.",
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

        if incident.taken_by is not None:
            return Response(
                {"error": "Cet incident est déjà pris en charge."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if incident.etat != 'declared':
            return Response(
                {"error": f"Impossible de prendre en charge un incident en état '{incident.etat}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prise en charge
        incident.taken_by = request.user
        incident.etat = 'taken_into_account'
        incident.save()

        # Créer la Collaboration leader accepted
        Collaboration.objects.create(
            incident=incident,
            user=request.user,
            role=COLLAB_ROLE_LEADER,
            status='accepted',
        )

        # Enregistrer l'action utilisateur
        action_message = f"took incident {incident_id} into account as leader"
        UserAction.objects.create(user=request.user, action=action_message)

        serializer = IncidentSerializer(incident)
        return Response({
            "status": "success",
            "message": action_message,
            "data": serializer.data,
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
