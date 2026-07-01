"""Category endpoints."""
from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='categories_retrieve',
        summary="Détail d'une catégorie",
        description="Retourne une catégorie par son identifiant. Accès public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de la catégorie")],
        request=None,
        responses={200: CategorySerializer, 404: OpenApiResponse(description="Catégorie introuvable")},
    ),
    put=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='categories_update',
        summary="Mettre à jour une catégorie",
        description="Met à jour une catégorie existante. Accès public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de la catégorie")],
        request=CategorySerializer,
        responses={
            200: CategorySerializer,
            400: OpenApiResponse(description="Données invalides"),
            404: OpenApiResponse(description="Catégorie introuvable"),
        },
    ),
    delete=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='categories_destroy',
        summary="Supprimer une catégorie",
        description="Supprime une catégorie. Refusé (400) si des incidents y sont rattachés. Accès public.",
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant de la catégorie")],
        request=None,
        responses={
            204: OpenApiResponse(description="Catégorie supprimée"),
            400: OpenApiResponse(description="Catégorie liée à des incidents (suppression refusée)"),
            404: OpenApiResponse(description="Catégorie introuvable"),
        },
    ),
)
class CategoryAPIView(APIView):
    permission_classes = ()
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get(self, request, id, format=None):
        try:
            category = Category.objects.get(id=id)
            serializer = CategorySerializer(category)
            return Response(serializer.data)
        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    def put(self, request, id, format=None):
        try:
            category = Category.objects.get(id=id)
            serializer = CategorySerializer(category, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id, format=None):
        try:
            category = Category.objects.get(id=id)
            
            # Check for associated incidents
            if Incident.objects.filter(category_id=category).exists():
                return Response(
                    {"error": "Cannot delete category with associated incidents"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            category.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

@extend_schema_view(
    get=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='categories_list',
        summary="Lister les catégories",
        description="Retourne la liste paginée des catégories. Accès public.",
        responses={
            200: CategorySerializer(many=True),
            500: OpenApiResponse(description="Erreur serveur"),
        },
    ),
    post=extend_schema(
        tags=['Catégories & Indicateurs'],
        operation_id='categories_create',
        summary="Créer une catégorie",
        description="Crée une nouvelle catégorie. Accès public.",
        request=CategorySerializer,
        responses={201: CategorySerializer, 400: OpenApiResponse(description="Données invalides")},
    ),
)
class CategoryAPIListView(generics.ListCreateAPIView):
    permission_classes = ()
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = PageNumberPagination

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

