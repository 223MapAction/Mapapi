"""Category endpoints."""
from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema(
    description="Endpoint allowing retrieval, updating, and deletion of a category.",
    request=CategorySerializer,
    responses={200: CategorySerializer, 404: "category not found"},  
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

@extend_schema(
    description="Endpoint allowing retrieval and creating of category.",
    request=CategorySerializer,
    responses={201: CategorySerializer, 400: "serializer error"},  
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

