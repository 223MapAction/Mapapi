"""Evenement endpoints."""
from rest_framework import status, generics
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination

from ..models import Evenement
from ..models import User
from ..serializer import EvenementSerializer


@extend_schema_view(
    get=extend_schema(
        tags=['Événements & Participation'],
        operation_id='events_retrieve',
        summary="Détails d'un événement",
        description="Retourne un événement par son id. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="id de l'événement"),
        ],
        responses={200: EvenementSerializer, 404: OpenApiResponse(description="Événement introuvable")},
    ),
    put=extend_schema(
        tags=['Événements & Participation'],
        operation_id='events_update',
        summary="Mettre à jour un événement",
        description="Met à jour entièrement un événement existant. `multipart/form-data` "
                    "pour `photo`/`video`/`audio`. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="id de l'événement"),
        ],
        request=EvenementSerializer,
        responses={
            200: EvenementSerializer,
            400: OpenApiResponse(description="Erreurs de validation"),
            404: OpenApiResponse(description="Événement introuvable"),
        },
    ),
    delete=extend_schema(
        tags=['Événements & Participation'],
        operation_id='events_destroy',
        summary="Supprimer un événement",
        description="Supprime un événement par son id. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="id de l'événement"),
        ],
        responses={
            204: OpenApiResponse(description="Événement supprimé"),
            404: OpenApiResponse(description="Événement introuvable"),
        },
    ),
    post=extend_schema(
        tags=['Événements & Participation'],
        operation_id='events_create_at_id',
        summary="Créer un événement (route /Event/<id>)",
        description="Hérité de `CreateAPIView` : crée un nouvel événement (l'id du chemin "
                    "est ignoré). Préférer `POST /Event/`. Endpoint public.",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                             description="ignoré"),
        ],
        request=EvenementSerializer,
        responses={201: EvenementSerializer, 400: OpenApiResponse(description="Erreurs de validation")},
    ),
)
class EvenementAPIView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Evenement.objects.all()
    serializer_class = EvenementSerializer
    
    def get(self, request, id, format=None):
        try:
            item = Evenement.objects.get(pk=id)
            serializer = EvenementSerializer(item)
            return Response(serializer.data)
        except Evenement.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = Evenement.objects.get(pk=id)
        except Evenement.DoesNotExist:
            return Response(status=404)
        serializer = EvenementSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = Evenement.objects.get(pk=id)
        except Evenement.DoesNotExist:
            return Response(status=404)
        item.delete()
        return Response(status=204)

@extend_schema_view(
    get=extend_schema(
        tags=['Événements & Participation'],
        operation_id='events_list',
        summary="Lister les événements",
        description="Retourne la liste paginée des événements (triés par id). Endpoint public.",
        responses={200: EvenementSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Événements & Participation'],
        operation_id='events_create',
        summary="Créer un événement",
        description="Crée un nouvel événement. `multipart/form-data` pour `photo`/`video`/"
                    "`audio` ; `user_id` (organisateur) requis. Effet de bord : +2 points "
                    "pour l'utilisateur. Endpoint public.",
        request=EvenementSerializer,
        responses={201: EvenementSerializer, 400: OpenApiResponse(description="Erreurs de validation")},
    ),
)
class EvenementAPIListView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Evenement.objects.all()
    serializer_class = EvenementSerializer

    def get(self, request, format=None):
        items = Evenement.objects.order_by('pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = EvenementSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        serializer = EvenementSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            user = User.objects.get(id=request.data["user_id"])
            user.points += 2
            user.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
