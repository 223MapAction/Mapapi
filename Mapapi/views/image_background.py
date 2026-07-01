"""Image background endpoints."""
from rest_framework import status, generics
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        tags=['Médias'],
        operation_id='media_image_retrieve',
        summary="Récupérer une image de fond",
        description="Renvoie une image de fond par son identifiant. Endpoint public (aucune authentification requise).",
        request=None,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'image de fond.")],
        responses={200: ImageBackgroundSerializer, 404: OpenApiResponse(description="Image introuvable (corps vide).")},
    ),
    put=extend_schema(
        tags=['Médias'],
        operation_id='media_image_update',
        summary="Mettre à jour une image de fond",
        description="Remplace une image de fond existante. Upload en `multipart/form-data` (champ `photo`). Endpoint public.",
        request=ImageBackgroundSerializer,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'image de fond.")],
        responses={
            200: ImageBackgroundSerializer,
            400: OpenApiResponse(description="Erreurs de validation du sérialiseur."),
            404: OpenApiResponse(description="Image introuvable (corps vide)."),
        },
    ),
    delete=extend_schema(
        tags=['Médias'],
        operation_id='media_image_destroy',
        summary="Supprimer une image de fond",
        description="Supprime définitivement une image de fond. Endpoint public.",
        request=None,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de l'image de fond.")],
        responses={
            204: OpenApiResponse(description="Image supprimée."),
            404: OpenApiResponse(description="Image introuvable (corps vide)."),
        },
    ),
)
class ImageBackgroundAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = ImageBackground.objects.all()
    serializer_class = ImageBackgroundSerializer

    def get(self, request, id, format=None):
        try:
            item = ImageBackground.objects.get(pk=id)
            serializer = ImageBackgroundSerializer(item)
            return Response(serializer.data)
        except ImageBackground.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = ImageBackground.objects.get(pk=id)
        except ImageBackground.DoesNotExist:
            return Response(status=404)
        serializer = ImageBackgroundSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = ImageBackground.objects.get(pk=id)
        except ImageBackground.DoesNotExist:
            return Response(status=404)
        item.delete()
        return Response(status=204)


@extend_schema_view(
    get=extend_schema(
        tags=['Médias'],
        operation_id='media_image_latest',
        summary="Récupérer la dernière image de fond",
        description="Renvoie la dernière image de fond enregistrée. Code de statut non idiomatique : la vue répond **201** (et non 200). Endpoint public.",
        request=None,
        responses={201: ImageBackgroundSerializer},
    ),
    post=extend_schema(
        tags=['Médias'],
        operation_id='media_image_create',
        summary="Créer une image de fond",
        description="Enregistre une nouvelle image de fond. Upload en `multipart/form-data` (champ `photo`). Endpoint public.",
        request=ImageBackgroundSerializer,
        responses={
            201: ImageBackgroundSerializer,
            400: OpenApiResponse(description="Erreurs de validation du sérialiseur."),
        },
    ),
)
class ImageBackgroundAPIListView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = ImageBackground.objects.all()
    serializer_class = ImageBackgroundSerializer

    def get(self, request, format=None):
        items = ImageBackground.objects.last()
        serializer = ImageBackgroundSerializer(items)
        return Response(serializer.data, status=201)

    def post(self, request, format=None):
        serializer = ImageBackgroundSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
    
