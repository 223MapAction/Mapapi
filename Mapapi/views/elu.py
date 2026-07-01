"""Elu endpoints."""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers

from ..serializer import *
from ..Send_mails import send_email
from .common import CustomPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        tags=['Contacts & Élus'],
        operation_id='elus_list',
        summary="Lister les élus",
        description="Renvoie la liste paginée des utilisateurs de type « élu ». Endpoint public.",
        request=None,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Présent dans l'URL mais non utilisé par la vue.")],
        responses={200: UserSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Contacts & Élus'],
        operation_id='elus_create',
        summary="Créer un élu",
        description="Crée un utilisateur « élu », l'associe éventuellement à des zones (champ `zones`), génère un mot de passe aléatoire et envoie les identifiants par e-mail. Endpoint public.",
        request=UserEluSerializer,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Présent dans l'URL mais non utilisé par la vue.")],
        responses={
            201: UserEluSerializer,
            400: OpenApiResponse(description="Erreurs de validation du sérialiseur."),
        },
    ),
)
class EluAPIListView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = User.objects.all()
    serializer_class = UserEluSerializer

    def get(self, request, format=None):
        items = User.objects.filter(user_type='elu').order_by('pk')
        paginator = PageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = UserSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        self.data = request.data.copy()
        if "zones" in request.data:
            self.data.pop('zones')

        serializer = UserEluSerializer(data=self.data)

        if serializer.is_valid():
            serializer.save()
            user = User.objects.get(id=serializer.data['id'])
            if "zones" in request.data:
                for id in request.data['zones']:
                    zone = Zone.objects.get(id=id)
                    if zone != None:
                        user.zones.add(zone)
            password = User.objects.make_random_password()
            user.set_password(password)
            user.save()

            subject, from_email, to = '[MAP ACTION] - Votre compte ÉLU', settings.EMAIL_HOST_USER, request.data["email"]
            html_content = render_to_string('mail_add_elu.html', {'email': request.data["email"],
                                                                  'password': password})  # render with dynamic value#
            text_content = strip_tags(html_content)  # Strip the html tag. So people can see the pure text at least.
            msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            return Response(UserEluSerializer(user).data, status=201)
        return Response(serializer.errors, status=400)

@extend_schema_view(
    get=extend_schema(
        tags=['Contacts & Élus'],
        operation_id='elus_zones_list',
        summary="Lister les attributions élu-zone",
        description="Renvoie la liste des attributions élu↔zone. Endpoint public.",
        request=None,
        responses={
            200: EluToZoneSerializer(many=True),
            500: OpenApiResponse(description="Erreur serveur : {\"error\": \"...\"}."),
        },
    ),
    post=extend_schema(
        tags=['Contacts & Élus'],
        operation_id='elus_assign_to_zone',
        summary="Attribuer une zone à un élu",
        description="Associe une zone à un élu à partir des identifiants `elu` et `zone` fournis dans le corps. Endpoint public.",
        request=EluToZoneSerializer,
        responses={
            200: inline_serializer(
                name='EluZoneAssignResponse',
                fields={'status': serializers.CharField(), 'message': serializers.CharField()},
            ),
            400: OpenApiResponse(description="Erreurs de validation du sérialiseur."),
            500: OpenApiResponse(description="Erreur serveur : {\"error\": \"...\"}."),
        },
    ),
)
class EluToZoneAPIListView(generics.ListCreateAPIView):
    permission_classes = ()
    queryset = User.objects.all()
    serializer_class = EluToZoneSerializer

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def post(self, request, format=None):
        try:
            elu = User.objects.get(id=request.data['elu'])
            zone = Zone.objects.get(id=request.data['zone'])
            if zone and elu:
                elu.zones.add(zone)
                return Response({
                    "status": "success",
                    "message": "elu attributed to zone"
                })
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

