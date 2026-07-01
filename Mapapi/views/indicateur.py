"""Indicator endpoints (CRUD + statistics on incidents)."""
from rest_framework import status, generics
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='indicators_retrieve',
        summary="Détail d'un indicateur",
        description="Retourne un indicateur par son identifiant. Accès public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'indicateur")],
        request=None,
        responses={200: IndicateurSerializer, 404: OpenApiResponse(description="Indicateur introuvable")},
    ),
    put=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='indicators_update',
        summary="Mettre à jour un indicateur",
        description="Met à jour un indicateur existant. Accès public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'indicateur")],
        request=IndicateurSerializer,
        responses={
            200: IndicateurSerializer,
            400: OpenApiResponse(description="Données invalides"),
            404: OpenApiResponse(description="Indicateur introuvable"),
        },
    ),
    delete=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='indicators_destroy',
        summary="Supprimer un indicateur",
        description="Supprime un indicateur. Accès public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'indicateur")],
        request=None,
        responses={
            204: OpenApiResponse(description="Indicateur supprimé"),
            404: OpenApiResponse(description="Indicateur introuvable"),
        },
    ),
    post=extend_schema(exclude=True),
)
class IndicateurAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Indicateur.objects.all()
    serializer_class = IndicateurSerializer

    def get(self, request, id, format=None):
        try:
            item = Indicateur.objects.get(pk=id)
            serializer = IndicateurSerializer(item)
            return Response(serializer.data)
        except Indicateur.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = Indicateur.objects.get(pk=id)
        except Indicateur.DoesNotExist:
            return Response(status=404)
        serializer = IndicateurSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = Indicateur.objects.get(pk=id)
        except Indicateur.DoesNotExist:
            return Response(status=404)
        item.delete()
        return Response(status=204)

@extend_schema_view(
    get=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='indicators_list',
        summary="Lister les indicateurs",
        description="Retourne la liste paginée des indicateurs. Accès public.",
        request=None,
        responses={200: IndicateurSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='indicators_create',
        summary="Créer un indicateur",
        description="Crée un nouvel indicateur. Accès public.",
        request=IndicateurSerializer,
        responses={201: IndicateurSerializer, 400: OpenApiResponse(description="Données invalides")},
    ),
)
class IndicateurAPIListView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Indicateur.objects.all()
    serializer_class = IndicateurSerializer

    def get(self, request, format=None):
        items = Indicateur.objects.order_by('pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = IndicateurSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        serializer = IndicateurSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

@extend_schema_view(
    get=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='indicators_incident_stats',
        summary="Statistiques incidents par indicateur",
        description="Retourne la répartition (nombre et pourcentage) des incidents par indicateur, sur l'ensemble des incidents. Accès public.",
        request=None,
        responses={200: inline_serializer(
            name='IndicatorsIncidentStatsResponse',
            fields={
                'status': serializers.CharField(),
                'message': serializers.CharField(),
                'data': inline_serializer(
                    name='IndicatorsIncidentStatItem',
                    fields={
                        'indicateur': serializers.CharField(),
                        'number': serializers.IntegerField(),
                        'pourcentage': serializers.FloatField(),
                    },
                    many=True,
                ),
            },
        )},
    ),
    post=extend_schema(exclude=True),
)
class IndicateurOnIncidentAPIListView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get(self, request, format=None):
        items = Indicateur.objects.all()
        total_incidents = Incident.objects.all().count()
        listData = []
        for item in items:
            # day_resolved = day_invs.filter(etat="resolved").count()
            incidents = Incident.objects.filter(indicateur_id=item.id)
            dataIndicateur = {"indicateur": item.name, "number": incidents.count(),
                              "pourcentage": (incidents.count() / total_incidents) * 100}
            listData.append(dataIndicateur)
        incidents_not_indic = Incident.objects.filter(indicateur_id__isnull=True)
        dataIndicateur = {"indicateur": "null", "number": incidents_not_indic.count(),
                          "pourcentage": (incidents_not_indic.count() / total_incidents) * 100}
        listData.append(dataIndicateur)
        return Response({
            "status": "success",
            "message": "indicateur % ",
            "data": listData
        }, status=status.HTTP_200_OK)

@extend_schema_view(
    get=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='indicators_incident_stats_by_zone',
        summary="Statistiques incidents par indicateur (zone)",
        description="Retourne la répartition des incidents par indicateur, restreinte à une zone. Accès public.",
        parameters=[OpenApiParameter('zone', OpenApiTypes.STR, OpenApiParameter.PATH, description="Nom de la zone")],
        request=None,
        responses={200: inline_serializer(
            name='IndicatorsIncidentStatsByZoneResponse',
            fields={
                'status': serializers.CharField(),
                'message': serializers.CharField(),
                'data': inline_serializer(
                    name='IndicatorsIncidentStatsByZoneItem',
                    fields={
                        'indicateur': serializers.CharField(),
                        'number': serializers.IntegerField(),
                        'pourcentage': serializers.FloatField(),
                    },
                    many=True,
                ),
            },
        )},
    ),
    post=extend_schema(exclude=True),
)
class IndicateurOnIncidentByZoneAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get(self, request, format=None, **kwargs):
        items = Indicateur.objects.all()
        zone = kwargs['zone']
        total_incidents = Incident.objects.filter(zone=zone).count()
        listData = []
        for item in items:
            # day_resolved = day_invs.filter(etat="resolved").count()
            incidents = Incident.objects.filter(indicateur_id=item.id, zone=zone)
            dataIndicateur = {"indicateur": item.name, "number": incidents.count(), "pourcentage": (
                                                                                                           incidents.count() / total_incidents) * 100 if incidents.count() > 0 else 0}
            listData.append(dataIndicateur)
        incidents_not_indic = Incident.objects.filter(indicateur_id__isnull=True, zone=zone)
        dataIndicateur = {"indicateur": "null", "number": incidents_not_indic.count(), "pourcentage": (
                                                                                                              incidents_not_indic.count() / total_incidents) * 100 if incidents_not_indic.count() > 0 else 0}
        listData.append(dataIndicateur)
        return Response({
            "status": "success",
            "message": "indicateur % ",
            "data": listData
        }, status=status.HTTP_200_OK)

@extend_schema_view(
    get=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='indicators_incident_stats_by_elu',
        summary="Statistiques incidents par indicateur (élu)",
        description="Retourne la répartition des incidents par indicateur pour les incidents signalés par un utilisateur (élu/organisation). Accès public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'utilisateur (élu/organisation)")],
        request=None,
        responses={200: inline_serializer(
            name='IndicatorsIncidentStatsByEluResponse',
            fields={
                'status': serializers.CharField(),
                'message': serializers.CharField(),
                'data': inline_serializer(
                    name='IndicatorsIncidentStatsByEluItem',
                    fields={
                        'indicateur': serializers.CharField(),
                        'number': serializers.IntegerField(),
                        'pourcentage': serializers.FloatField(),
                    },
                    many=True,
                ),
            },
        )},
    ),
    post=extend_schema(exclude=True),
)
class IndicateurOnIncidentByEluAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer

    def get(self, request, id, format=None, **kwargs):
        items = Indicateur.objects.all()
        total_incidents = Incident.objects.filter(user_id=id).count()
        listData = []
        for item in items:
            # day_resolved = day_invs.filter(etat="resolved").count()
            incidents = Incident.objects.filter(indicateur_id=item.id, user_id=id)
            dataIndicateur = {"indicateur": item.name, "number": incidents.count(), "pourcentage": (
                                                                                                           incidents.count() / total_incidents) * 100 if incidents.count() > 0 else 0}
            listData.append(dataIndicateur)
        incidents_not_indic = Incident.objects.filter(indicateur_id__isnull=True, user_id=id)
        dataIndicateur = {"indicateur": "null", "number": incidents_not_indic.count(), "pourcentage": (
                                                                                                              incidents_not_indic.count() / total_incidents) * 100 if incidents_not_indic.count() > 0 else 0}
        listData.append(dataIndicateur)
        return Response({
            "status": "success",
            "message": "indicateur % ",
            "data": listData
        }, status=status.HTTP_200_OK)
