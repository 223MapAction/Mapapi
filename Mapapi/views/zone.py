"""Zone endpoints."""
from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        tags=['Zones'],
        operation_id='zones_retrieve',
        summary="Détails d'une zone",
        description="Retourne une zone par son id. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="id de la zone"),
        ],
        responses={200: ZoneSerializer, 404: OpenApiResponse(description="Zone introuvable")},
    ),
    put=extend_schema(
        tags=['Zones'],
        operation_id='zones_update',
        summary="Mettre à jour une zone",
        description="Met à jour entièrement une zone existante. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="id de la zone"),
        ],
        request=ZoneSerializer,
        responses={
            200: ZoneSerializer,
            400: OpenApiResponse(description="Erreurs de validation"),
            404: OpenApiResponse(description="Zone introuvable"),
        },
    ),
    delete=extend_schema(
        tags=['Zones'],
        operation_id='zones_destroy',
        summary="Supprimer une zone",
        description="Supprime une zone par son id. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="id de la zone"),
        ],
        responses={
            204: OpenApiResponse(description="Zone supprimée"),
            404: OpenApiResponse(description="Zone introuvable"),
        },
    ),
    post=extend_schema(
        tags=['Zones'],
        operation_id='zones_create_at_id',
        summary="Créer une zone (route /zone/<id>)",
        description="Hérité de `CreateAPIView` : crée une nouvelle zone (l'id du chemin "
                    "est ignoré). Préférer `POST /zone/`. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="ignoré"),
        ],
        request=ZoneSerializer,
        responses={201: ZoneSerializer, 400: OpenApiResponse(description="Erreurs de validation")},
    ),
)
class ZoneAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer

    def get(self, request, id, format=None):
        try:
            item = Zone.objects.get(pk=id)
            serializer = ZoneSerializer(item)
            return Response(serializer.data)
        except Zone.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = Zone.objects.get(pk=id)
        except Zone.DoesNotExist:
            return Response(status=404)
        serializer = ZoneSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = Zone.objects.get(pk=id)
        except Zone.DoesNotExist:
            return Response(status=404)
        item.delete()
        return Response(status=204)

@extend_schema_view(
    get=extend_schema(
        tags=['Zones'],
        operation_id='zones_list',
        summary="Lister les zones",
        description="Retourne la liste paginée des zones. Endpoint public.",
        responses={
            200: ZoneSerializer(many=True),
            500: OpenApiResponse(description="Erreur serveur (`{error}`)"),
        },
    ),
    post=extend_schema(
        tags=['Zones'],
        operation_id='zones_create',
        summary="Créer une zone",
        description="Crée une nouvelle zone. Endpoint public.",
        request=ZoneSerializer,
        responses={201: ZoneSerializer, 400: OpenApiResponse(description="Erreurs de validation")},
    ),
)
class ZoneAPIListView(generics.ListCreateAPIView):
    permission_classes = (
    )
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer
    pagination_class = PageNumberPagination

    def get(self, request, format=None, *args, **kwargs):
        try:
            return self.list(request, *args, **kwargs)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, format=None, *args, **kwargs):
        serializer = ZoneSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

