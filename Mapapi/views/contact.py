"""Contact endpoints."""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from rest_framework import status, generics
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from .common import CustomPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        tags=['Contacts & Élus'],
        operation_id='contacts_retrieve',
        summary="Récupérer un contact",
        description="Renvoie un message de contact par son identifiant. Endpoint public (aucune authentification requise).",
        request=None,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant du contact.")],
        responses={200: ContactSerializer, 404: OpenApiResponse(description="Contact introuvable (corps vide).")},
    ),
    put=extend_schema(
        tags=['Contacts & Élus'],
        operation_id='contacts_update',
        summary="Mettre à jour un contact",
        description="Remplace l'intégralité d'un message de contact existant. Endpoint public.",
        request=ContactSerializer,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant du contact.")],
        responses={
            200: ContactSerializer,
            400: OpenApiResponse(description="Erreurs de validation du sérialiseur."),
            404: OpenApiResponse(description="Contact introuvable (corps vide)."),
        },
    ),
    delete=extend_schema(
        tags=['Contacts & Élus'],
        operation_id='contacts_destroy',
        summary="Supprimer un contact",
        description="Supprime définitivement un message de contact. Endpoint public.",
        request=None,
        parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH, description="Identifiant du contact.")],
        responses={
            204: OpenApiResponse(description="Contact supprimé."),
            404: OpenApiResponse(description="Contact introuvable (corps vide)."),
        },
    ),
)
class ContactAPIView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    
    def get(self, request, id, format=None):
        try:
            item = Contact.objects.get(pk=id)
            serializer = ContactSerializer(item)
            return Response(serializer.data)
        except Contact.DoesNotExist:
            return Response(status=404)

    def put(self, request, id, format=None):
        try:
            item = Contact.objects.get(pk=id)
        except Contact.DoesNotExist:
            return Response(status=404)
        serializer = ContactSerializer(item, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, id, format=None):
        try:
            item = Contact.objects.get(pk=id)
        except Contact.DoesNotExist:
            return Response(status=404)
        item.delete()
        return Response(status=204)

@extend_schema_view(
    get=extend_schema(
        tags=['Contacts & Élus'],
        operation_id='contacts_list',
        summary="Lister les contacts",
        description="Renvoie la liste paginée des messages de contact. Endpoint public.",
        request=None,
        responses={200: ContactSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Contacts & Élus'],
        operation_id='contacts_create',
        summary="Créer un contact",
        description="Crée un message de contact puis envoie un e-mail de notification aux administrateurs. Endpoint public.",
        request=ContactSerializer,
        responses={
            201: ContactSerializer,
            400: OpenApiResponse(description="Erreurs de validation du sérialiseur."),
        },
    ),
)
class ContactAPIListView(generics.CreateAPIView):
    permission_classes = ()
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    
    def get(self, request, format=None):
        items = Contact.objects.order_by('pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = ContactSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        serializer = ContactSerializer(data=request.data)
        admins = User.objects.filter(user_type="admin").values_list('email', flat=True)
        if serializer.is_valid():
            serializer.save()

            subject, from_email, to = '[MAP ACTION] - Nouveau Message', settings.EMAIL_HOST_USER, request.data["email"]
            html_content = render_to_string('mail_new_message.html')
            text_content = strip_tags(html_content)
            msg = EmailMultiAlternatives(subject, text_content, from_email, list(admins))
            msg.attach_alternative(html_content, "text/html")
            msg.send()

            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
