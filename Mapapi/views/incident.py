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
)
from ..permissions import IsIncidentLeader
from .common import CustomPageNumberPagination


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
        item.delete()
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
        return Response({
            "status": "success",
            "message": f"Incident {incident_id} clôturé.",
            "data": serializer.data,
        }, status=status.HTTP_200_OK)
