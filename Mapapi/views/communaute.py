"""Communaute (community) endpoints."""
from rest_framework import status, generics
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='communities_retrieve',
        summary="Récupérer une communauté",
        description="Renvoie une communauté par son identifiant. Endpoint public (aucune authentification requise).",
        request=None,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de la communauté.")],
        responses={200: CommunauteSerializer, 404: OpenApiResponse(description="Communauté introuvable (corps vide).")},
    ),
    put=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='communities_update',
        summary="Mettre à jour une communauté",
        description="Remplace l'intégralité d'une communauté existante. Endpoint public.",
        request=CommunauteSerializer,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de la communauté.")],
        responses={
            200: CommunauteSerializer,
            400: OpenApiResponse(description="Erreurs de validation du sérialiseur."),
            404: OpenApiResponse(description="Communauté introuvable (corps vide)."),
        },
    ),
    delete=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='communities_destroy',
        summary="Supprimer une communauté",
        description="Supprime définitivement une communauté. Endpoint public.",
        request=None,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de la communauté.")],
        responses={
            204: OpenApiResponse(description="Communauté supprimée."),
            404: OpenApiResponse(description="Communauté introuvable (corps vide)."),
        },
    ),
)
class CommunauteAPIView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Communaute.objects.all()
    serializer_class = CommunauteSerializer
    
    def get(self, request, id, format=None):
        try:
            item = Communaute.objects.get(pk=id)
            serializer = CommunauteSerializer(item)
            return Response(serializer.data)
        except Communaute.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = Communaute.objects.get(pk=id)
        except Communaute.DoesNotExist:
            return Response(status=404)
        serializer = CommunauteSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = Communaute.objects.get(pk=id)
        except Communaute.DoesNotExist:
            return Response(status=404)
        item.delete()
        return Response(status=204)

@extend_schema_view(
    get=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='communities_list',
        summary="Lister les communautés",
        description="Renvoie la liste paginée des communautés. Endpoint public.",
        request=None,
        responses={200: CommunauteSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Messages & Communauté'],
        operation_id='communities_create',
        summary="Créer une communauté",
        description="Crée une nouvelle communauté. Endpoint public.",
        request=CommunauteSerializer,
        responses={
            201: CommunauteSerializer,
            400: OpenApiResponse(description="Erreurs de validation du sérialiseur."),
        },
    ),
)
class CommunauteAPIListView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Communaute.objects.all()
    serializer_class = CommunauteSerializer
    
    def get(self, request, format=None):
        items = Communaute.objects.order_by('pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = CommunauteSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        serializer = CommunauteSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
