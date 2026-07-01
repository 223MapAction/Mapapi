"""Participate endpoints."""
from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        tags=['Événements & Participation'],
        operation_id='participations_retrieve',
        summary="Détails d'une participation",
        description="Retourne une participation par son id. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="id de la participation"),
        ],
        responses={200: ParticipateSerializer, 404: OpenApiResponse(description="Participation introuvable")},
    ),
    put=extend_schema(
        tags=['Événements & Participation'],
        operation_id='participations_update',
        summary="Mettre à jour une participation",
        description="Met à jour entièrement une participation existante. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="id de la participation"),
        ],
        request=ParticipateSerializer,
        responses={
            200: ParticipateSerializer,
            400: OpenApiResponse(description="Erreurs de validation"),
            404: OpenApiResponse(description="Participation introuvable"),
        },
    ),
    delete=extend_schema(
        tags=['Événements & Participation'],
        operation_id='participations_destroy',
        summary="Supprimer une participation",
        description="Supprime une participation par son id. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="id de la participation"),
        ],
        responses={
            204: OpenApiResponse(description="Participation supprimée"),
            404: OpenApiResponse(description="Participation introuvable"),
        },
    ),
    post=extend_schema(
        tags=['Événements & Participation'],
        operation_id='participations_create_at_id',
        summary="Créer une participation (route /participate/<id>)",
        description="Hérité de `CreateAPIView` : crée une nouvelle participation (l'id du "
                    "chemin est ignoré). Préférer `POST /participate/`. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="ignoré"),
        ],
        request=ParticipateSerializer,
        responses={201: ParticipateSerializer, 400: OpenApiResponse(description="Erreurs de validation")},
    ),
)
class ParticipateAPIView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = Participate.objects.all()
    serializer_class = ParticipateSerializer

    def get(self, request, id, format=None):
        try:
            item = Participate.objects.get(pk=id)
            serializer = ParticipateSerializer(item)
            return Response(serializer.data)
        except Participate.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = Participate.objects.get(pk=id)
        except Participate.DoesNotExist:
            return Response(status=404)
        serializer = ParticipateSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = Participate.objects.get(pk=id)
        except Participate.DoesNotExist:
            return Response(status=404)
        item.delete()
        return Response(status=204)

@extend_schema_view(
    get=extend_schema(
        tags=['Événements & Participation'],
        operation_id='participations_list',
        summary="Lister les participations",
        description="Retourne la liste paginée des participations (10 par page). Endpoint public.",
        responses={200: ParticipateSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Événements & Participation'],
        operation_id='participations_create',
        summary="Créer une participation",
        description="Crée une participation à un événement. Effet de bord : +1 point pour "
                    "l'utilisateur référencé par `user_id`. Endpoint public.",
        request=ParticipateSerializer,
        responses={201: ParticipateSerializer, 400: OpenApiResponse(description="Erreurs de validation")},
    ),
)
class ParticipateAPIListView(generics.ListCreateAPIView):
    permission_classes = ()
    queryset = Participate.objects.all()
    serializer_class = ParticipateSerializer
    pagination_class = PageNumberPagination

    def get(self, request, *args, **kwargs):
        self.pagination_class.page_size = 10  # Nombre d'éléments par page
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        serializer = ParticipateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            user = User.objects.get(id=request.data["user_id"])
            user.points += 1
            user.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

