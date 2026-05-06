"""Image background endpoints."""
from rest_framework import status, generics
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from ..serializer import *
from .common import CustomPageNumberPagination


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
    
