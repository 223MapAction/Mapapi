"""Evenement endpoints."""
from rest_framework import status, generics
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from ..serializer import *
from .common import CustomPageNumberPagination

from ..models import Evenement
from ..models import User
from ..serializer import EvenementSerializer


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
