"""Zone endpoints."""
from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema(
    description="Endpoint allowing retrival, updating and deletion of zone.",
    responses={200: ZoneSerializer, 404: "zone not found"},  
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

@extend_schema(
    description="Endpoint allowing retrival and creating of zone.",
    request=ZoneSerializer,
    responses={201: ZoneSerializer, 400: "Bad request"},  
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

