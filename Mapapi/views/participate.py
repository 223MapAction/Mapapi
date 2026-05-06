"""Participate endpoints."""
from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema(
    description="Endpoint allowing retrieval, updating, and deletion of participation.",
    request=ParticipateSerializer,
    responses={200: ParticipateSerializer, 404: "Participation not found"},  
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

@extend_schema(
    description="Endpoint allowing retrieval and creating of participation.",
    request=ParticipateSerializer,
    responses={201: ParticipateSerializer, 400: "serializer error"},  
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

