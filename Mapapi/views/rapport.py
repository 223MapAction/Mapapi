"""Rapport endpoints (CRUD, by user, by zone)."""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse,
    OpenApiExample, inline_serializer,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        tags=['Rapports'],
        operation_id='rapports_retrieve',
        summary="Détail d'un rapport",
        description="Retourne un rapport par son identifiant. Accès public (aucune permission requise).",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant du rapport")],
        request=None,
        responses={200: RapportSerializer, 404: OpenApiResponse(description="Rapport introuvable")},
    ),
    put=extend_schema(
        tags=['Rapports'],
        operation_id='rapports_update',
        summary="Mettre à jour un rapport",
        description="Met à jour partiellement un rapport. Si 'disponible' est vrai ou si un 'file' est fourni, le rapport est marqué disponible et un e-mail est envoyé au demandeur. Accès public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant du rapport")],
        request=RapportSerializer,
        responses={
            200: RapportSerializer,
            400: OpenApiResponse(description="Données invalides"),
            404: OpenApiResponse(description="Rapport introuvable"),
        },
    ),
    delete=extend_schema(
        tags=['Rapports'],
        operation_id='rapports_destroy',
        summary="Supprimer un rapport",
        description="Supprime définitivement un rapport. Accès public (aucune permission requise).",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant du rapport")],
        request=None,
        responses={
            204: OpenApiResponse(description="Rapport supprimé"),
            404: OpenApiResponse(description="Rapport introuvable"),
        },
    ),
    post=extend_schema(exclude=True),
)
class RapportAPIView(generics.CreateAPIView):
    queryset = Rapport.objects.all()
    serializer_class = RapportSerializer
    
    def get(self, request, id, format=None):
        try:
            item = Rapport.objects.get(pk=id)
            serializer = RapportSerializer(item)
            return Response(serializer.data)
        except Rapport.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = Rapport.objects.get(pk=id)
        except Rapport.DoesNotExist:
            return Response(status=404)
        serializer = RapportSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            if 'disponible' in request.data and request.data['disponible'] == True:
                if serializer.data['user_id']:
                    user = User.objects.get(id=serializer.data['user_id'])
                    subject, from_email, to = 'Commande de rapport disponible', settings.EMAIL_HOST_USER, user.email
                    html_content = render_to_string('mail_commande_disp.html', {
                        'details': serializer.data['details']})
                    text_content = strip_tags(
                        html_content)
                    msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
                    msg.attach_alternative(html_content, "text/html")
                    msg.send()
                return Response(serializer.data)
            if 'file' in request.data:
                if serializer.data['user_id']:
                    item.disponible = True
                    item.save()
                    user = User.objects.get(id=serializer.data['user_id'])
                    subject, from_email, to = 'Commande de rapport disponible', settings.EMAIL_HOST_USER, user.email
                    html_content = render_to_string('mail_commande_disp.html', {
                        'details': serializer.data['details']})
                    text_content = strip_tags(
                        html_content)
                    msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
                    msg.attach_alternative(html_content, "text/html")
                    msg.send()
                serializer = RapportSerializer(item).data
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = Rapport.objects.get(pk=id)
        except Rapport.DoesNotExist:
            return Response(status=404)
        item.delete()
        return Response(status=204)

@extend_schema_view(
    get=extend_schema(
        tags=['Rapports'],
        operation_id='rapports_list',
        summary="Lister les rapports",
        description="Retourne la liste paginée de tous les rapports (l'utilisateur demandeur est imbriqué). Accès public.",
        request=None,
        responses={200: RapportGetSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Rapports'],
        operation_id='rapports_create',
        summary="Créer une commande de rapport",
        description="Crée un rapport et notifie les administrateurs par e-mail. Accès public.",
        request=RapportSerializer,
        responses={201: RapportSerializer, 400: OpenApiResponse(description="Données invalides")},
    ),
)
class RapportAPIListView(generics.CreateAPIView):
    queryset = Rapport.objects.all()
    serializer_class = RapportSerializer
    
    def get(self, request, format=None):
        items = Rapport.objects.order_by('pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = RapportGetSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        serializer = RapportSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            admins = User.objects.filter(user_type="admin").values_list('email', flat=True)
            # print("admins: ",list(admins))
            incident = Incident.objects.get(id=request.data['incident'])
            subject, from_email, to = '[MAP ACTION] - Nouvelle commande de rapport', settings.EMAIL_HOST_USER, user.email
            html_content = render_to_string('mail_rapport_admin.html',
                                            {'details': incident.title})  # render with dynamic value#
            text_content = strip_tags(html_content)  # Strip the html tag. So people can see the pure text at least.
            msg = EmailMultiAlternatives(subject, text_content, from_email, list(admins))
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

@extend_schema_view(
    get=extend_schema(
        tags=['Rapports'],
        operation_id='rapports_by_user',
        summary="Rapports d'un utilisateur",
        description="Retourne tous les rapports commandés par l'utilisateur donné. Accès public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'utilisateur demandeur")],
        request=None,
        responses={200: RapportGetSerializer(many=True)},
    ),
    post=extend_schema(exclude=True),
)
class RapportByUserAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Rapport.objects.all()
    serializer_class = RapportSerializer
    
    def get(self, request, id, format=None, **kwargs):
        try:
            item = Rapport.objects.filter(user_id=id)
            serializer = RapportGetSerializer(item, many=True)
            return Response(serializer.data)
        except Rapport.DoesNotExist:
            return Response(status=404)

@extend_schema_view(
    get=extend_schema(
        tags=['Rapports'],
        operation_id='rapports_zone_list',
        summary="Lister les rapports de zone",
        description="Retourne la liste paginée des rapports de type 'zone'. Accès public.",
        request=None,
        responses={200: RapportGetSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Rapports'],
        operation_id='rapports_zone_create',
        summary="Créer un rapport de zone",
        description="Crée un rapport de type 'zone' et y rattache automatiquement tous les incidents de la zone, puis notifie les administrateurs. Requiert type='zone' et le champ 'zone'. Accès public.",
        request=RapportSerializer,
        responses={
            200: inline_serializer(
                name='RapportsZoneCreateResponse',
                fields={
                    'status': serializers.CharField(),
                    'message': serializers.CharField(),
                    'data': RapportSerializer(),
                },
            ),
            400: OpenApiResponse(description="Données invalides"),
            404: OpenApiResponse(description="type différent de 'zone' ou champ 'zone' manquant"),
        },
        examples=[
            OpenApiExample(
                'Rapport de zone',
                value={'type': 'zone', 'zone': 'Bamako', 'details': 'Synthèse de la zone'},
                request_only=True,
            ),
        ],
    ),
)
class RapportOnZoneAPIView(generics.CreateAPIView):
    queryset = Rapport.objects.all()
    serializer_class = RapportSerializer
    
    def get(self, request, format=None):
        items = Rapport.objects.filter(type="zone").order_by('pk')
        paginator = PageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = RapportGetSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        if request.data['type'] == 'zone' and 'zone' in request.data:
            serializer = RapportSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()

                rapport = Rapport.objects.get(id=serializer.data['id'])
                incidents = Incident.objects.filter(zone=request.data['zone'])
                for i in incidents:
                    rapport.incidents.add(i.id)
                # print(rapport.incidents)
                rapport.save()
                data = RapportSerializer(rapport).data

                admins = User.objects.filter(user_type="admin").values_list('email', flat=True)
                subject, from_email = '[MAP ACTION] - Nouveau Rapport', settings.EMAIL_HOST_USER
                html_content = render_to_string('mail_new_rapport.html')  # render with dynamic value#
                text_content = strip_tags(html_content)  # Strip the html tag. So people can see the pure text at least.
                msg = EmailMultiAlternatives(subject, text_content, from_email, list(admins))
                msg.attach_alternative(html_content, "text/html")
                msg.send()

                return Response({
                    "status": "success",
                    "message": "item successfully created",
                    "data": data
                }, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=400)
        else:
            return Response(status=404)
