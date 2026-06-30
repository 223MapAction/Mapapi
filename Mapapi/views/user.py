"""User & authentication endpoints (register, login, password reset, OTP, profile)."""
import os
import time
import requests
from datetime import timedelta

import pyotp

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import strip_tags
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from ..roles import is_super_admin, is_org_admin
from ..models import ORG_ROLE_BUREAU, ORG_ROLE_FIELD
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken

from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse,
    OpenApiExample, inline_serializer,
)
from drf_spectacular.types import OpenApiTypes

from ..serializer import *
from rest_framework import serializers
from ..Send_mails import send_email
from .common import CustomPageNumberPagination, get_random, logger


class GetTokenByMailView(generics.CreateAPIView):
    permission_classes = ()
    queryset = User.objects.all()
    serializer_class = UserSerializer

    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_get_token_by_mail',
        summary="Obtenir un token par email",
        description="Émet un token d'accès JWT à partir d'un email seul, sans "
                    "vérification du mot de passe (faiblesse de sécurité connue). "
                    "Endpoint public.",
        request=inline_serializer(
            name='GetTokenByMailRequest',
            fields={'email': serializers.EmailField()},
        ),
        responses={
            201: inline_serializer(
                name='GetTokenByMailResponse',
                fields={
                    'status': serializers.CharField(),
                    'message': serializers.CharField(),
                    'token': serializers.CharField(),
                },
            ),
            404: OpenApiResponse(description="Aucun utilisateur avec cet email."),
        },
    )
    def post(self, request, *args, **kwargs):
        try:
            item = User.objects.get(email=request.data['email'])
        except User.DoesNotExist:
            return Response(status=404)
        
        token = AccessToken.for_user(item)
        
        return Response({
            "status": "success",
            "message": "item successfully created",
            'token': str(token)
        }, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@extend_schema(
    description="Endpoint allowing user login. Authenticates user with provided email and password.",
    request=None,  
    responses={200: UserSerializer, 401: "Unauthorized"},
    parameters=[
        OpenApiParameter(name='email', description='User email', required=True, type=str),
        OpenApiParameter(name='password', description='User password', required=True, type=str),
    ]
)
def login_view(request):
    if request.method == 'POST':
        email = request.data.get('email')
        password = request.data.get('password')

        user = authenticate(email=email, password=password)
        if user:
            refresh = RefreshToken.for_user(user)
            token = {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
            return Response({'user': UserSerializer(user).data, 'token': token}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

@extend_schema(
    methods=['GET'],
    tags=['Utilisateurs & Profil'],
    operation_id='users_register_list',
    summary="Lister tous les utilisateurs",
    description="Retourne la liste complète des utilisateurs. Endpoint public.",
    request=None,
    responses={200: UserSerializer(many=True)},
)
@extend_schema(
    methods=['POST'],
    tags=['Authentification'],
    operation_id='auth_register',
    summary="Inscription d'un utilisateur",
    description="Crée un compte utilisateur et retourne l'utilisateur créé avec "
                "un couple de tokens JWT (connexion automatique). Endpoint public.",
    request=UserRegisterSerializer,
    responses={
        201: inline_serializer(
            name='RegisterResponse',
            fields={
                'user': UserRegisterSerializer(),
                'token': inline_serializer(
                    name='RegisterTokenPair',
                    fields={
                        'refresh': serializers.CharField(),
                        'access': serializers.CharField(),
                    },
                ),
            },
        ),
        400: OpenApiResponse(description="Données invalides."),
    },
    examples=[
        OpenApiExample(name='User', value={
            'first_name': 'Annoura',
            'last_name': 'Toure',
            'phone': '20303020',
            'address': 'Mali',
            'email': 'john@example.com',
            'password': 'secret_password'
        })
    ],
)
@api_view(['GET', 'POST'])
def UserRegisterView(request):
    if request.method == 'GET':
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    if request.method == 'POST':
        serializer = UserRegisterSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            token = {
                'refresh': str(refresh),
                'access': str(refresh.access_token)
            }
            return Response({'user': serializer.data, 'token': token}, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(
    methods=['GET'],
    tags=['Utilisateurs & Profil'],
    operation_id='users_retrieve',
    summary="Récupérer un utilisateur",
    description="Retourne un utilisateur par son identifiant. Endpoint public.",
    parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                                 description="Identifiant de l'utilisateur")],
    request=None,
    responses={200: UserSerializer, 404: OpenApiResponse(description="Utilisateur introuvable.")},
)
@extend_schema(
    methods=['PUT'],
    tags=['Utilisateurs & Profil'],
    operation_id='users_update',
    summary="Mettre à jour un utilisateur",
    description="Met à jour partiellement un utilisateur. Si 'password' est "
                "fourni, il est haché avant enregistrement. Endpoint public.",
    parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                                 description="Identifiant de l'utilisateur")],
    request=UserPutSerializer,
    responses={
        200: UserPutSerializer,
        400: OpenApiResponse(description="Données invalides."),
        404: OpenApiResponse(description="Utilisateur introuvable."),
    },
)
@extend_schema(
    methods=['DELETE'],
    tags=['Utilisateurs & Profil'],
    operation_id='users_delete',
    summary="Supprimer un utilisateur",
    description="Supprime définitivement un utilisateur. Endpoint public.",
    parameters=[OpenApiParameter('id', OpenApiTypes.UUID, OpenApiParameter.PATH,
                                 description="Identifiant de l'utilisateur")],
    request=None,
    responses={
        204: OpenApiResponse(description="Utilisateur supprimé."),
        404: OpenApiResponse(description="Utilisateur introuvable."),
    },
)
def _can_edit_user(actor, target):
    """Modification autorisée : soi-même, l'admin de SON organisation, ou le Super Admin."""
    if is_super_admin(actor):
        return True
    if actor.id == target.id:
        return True
    actor_org = getattr(actor, 'organisation_member_id', None)
    return bool(
        actor_org
        and actor_org == getattr(target, 'organisation_member_id', None)
        and is_org_admin(actor)
        and not getattr(target, 'is_superuser', False)
    )


def _can_delete_user(actor, target):
    """Suppression autorisée :
      - Super Admin : n'importe quel utilisateur.
      - Admin d'organisation : les membres de SON organisation (jamais un Super Admin).
      - Agent de bureau : uniquement les agents de TERRAIN de son organisation (jamais un admin).
      - Autres rôles : personne.
    """
    if is_super_admin(actor):
        return True
    if getattr(target, 'is_superuser', False):
        return False  # seul un Super Admin peut supprimer un Super Admin
    actor_org = getattr(actor, 'organisation_member_id', None)
    same_org = bool(actor_org and actor_org == getattr(target, 'organisation_member_id', None))
    if not same_org:
        return False
    if is_org_admin(actor):
        return True
    if getattr(actor, 'org_role', None) == ORG_ROLE_BUREAU:
        return target.org_role == ORG_ROLE_FIELD
    return False


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def user_api_view(request, id):
    if request.method == 'GET':
        try:
            item = User.objects.get(pk=id)
            serializer = UserSerializer(item)
            return Response(serializer.data)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PUT':
        try:
            item = User.objects.get(pk=id)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not _can_edit_user(request.user, item):
            return Response({'error': "Vous n'avez pas les droits pour modifier cet utilisateur."},
                            status=status.HTTP_403_FORBIDDEN)
        data = request.data.copy()
        if "password" in request.data:
            item.set_password(request.data['password'])
            data['password'] = item.password

        serializer = UserPutSerializer(item, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        try:
            item = User.objects.get(pk=id)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not _can_delete_user(request.user, item):
            return Response({'error': "Vous n'avez pas les droits pour supprimer cet utilisateur."},
                            status=status.HTTP_403_FORBIDDEN)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@extend_schema_view(
    get=extend_schema(
        tags=['Utilisateurs & Profil'],
        operation_id='users_list',
        summary="Lister les utilisateurs (paginé)",
        description="Retourne la liste paginée des utilisateurs triés par "
                    "identifiant. Endpoint public.",
        responses={200: UserSerializer(many=True)},
    ),
    post=extend_schema(
        tags=['Utilisateurs & Profil'],
        operation_id='users_create',
        summary="Créer un utilisateur",
        description="Crée un utilisateur. Accepte une liste optionnelle 'zones' "
                    "(ids) et envoie un email de bienvenue lorsque 'user_type' "
                    "est fourni. Endpoint public.",
        request=UserSerializer,
        responses={201: UserSerializer, 400: OpenApiResponse(description="Données invalides.")},
    ),
)
class UserAPIListView(generics.CreateAPIView):
    permission_classes = ()
    queryset = User.objects.all()
    serializer_class = UserSerializer
    
    def get(self, request, format=None):
        items = User.objects.order_by('pk')
        paginator = CustomPageNumberPagination()
        result_page = paginator.paginate_queryset(items, request)
        serializer = UserSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, format=None):
        start_time = time.time()
        data = request.data.copy()
        zones = data.pop('zones', None)

        logger.info("Starting user creation process")
        serializer = UserSerializer(data=data)
        if serializer.is_valid():
            user = serializer.save()
            if zones:
                user.zones.set(zones)
            user_creation_time = time.time() - start_time
            logger.info(f"User created in {user_creation_time:.2f} seconds")

            user_type = request.data.get('user_type', None)
            if user_type:
                subject_prefix = '[MAP ACTION] - Création de Compte'
                email_template = 'mail_add_account.html'
                usertype = user_type.upper()

                if user_type == "admin":
                    subject = f'{subject_prefix} Admin'
                    email_template = 'mail_add_admin.html'
                else:
                    subject = f'{subject_prefix} Organisation'

                context = {'email': request.data["email"], 'password': request.data["password"], 'usertype': usertype}

                send_email.delay(subject, email_template, context, request.data["email"])
                logger.info("Email task queued")

            total_time = time.time() - start_time
            logger.info(f"Total processing time: {total_time:.2f} seconds")

            return Response(serializer.data, status=201)

        return Response(serializer.errors, status=400)

@extend_schema_view(get=extend_schema(
    tags=['Utilisateurs & Profil'],
    operation_id='users_citizens_list',
    summary="Lister les citoyens",
    description="Retourne la liste paginée des utilisateurs de type 'citizen' "
                "(10 par page). Endpoint public.",
    responses={200: UserSerializer(many=True)},
))
class CitizenAPIListView(generics.ListAPIView):
    permission_classes = ()
    queryset = User.objects.filter(user_type='citizen').order_by('pk')
    serializer_class = UserSerializer
    pagination_class = PageNumberPagination

    def get(self, request, *args, **kwargs):
        self.pagination_class.page_size = 10  # Modifier ici pour définir la taille de la page
        return self.list(request, *args, **kwargs)

@extend_schema_view(get=extend_schema(
    tags=['Utilisateurs & Profil'],
    operation_id='users_me',
    summary="Utilisateur courant",
    description="Retourne l'utilisateur authentifié, enveloppé dans "
                "{status, message, data}. Les champs sensibles (mot de passe, "
                "otp, pin, token de vérification) ne sont jamais exposés. "
                "Authentification requise.",
    responses={
        200: inline_serializer(
            name='CurrentUserResponse',
            fields={
                'status': serializers.CharField(),
                'message': serializers.CharField(),
                'data': UserSerializer(),
            },
        ),
        400: OpenApiResponse(description="Utilisateur introuvable."),
    },
))
class UserRetrieveView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = (
        permissions.IsAuthenticated,
    )

    def get(self, request, *args, **kwargs):
        user = User.objects.get(email=request.user.email)

        if not user:
            return Response({
                "status": "failure",
                "message": "no such item",
            }, status=status.HTTP_400_BAD_REQUEST)

        data = UserSerializer(user).data

        return Response({
            "status": "success",
            "message": "item successfully created",
            "data": data
        }, status=status.HTTP_200_OK)

@extend_schema_view(
    put=extend_schema(
        tags=['Authentification'],
        operation_id='auth_change_password',
        summary="Changer le mot de passe",
        description="Change le mot de passe de l'utilisateur authentifié après "
                    "vérification de l'ancien mot de passe. Authentification requise.",
        request=ChangePasswordSerializer,
        responses={
            200: inline_serializer(
                name='ChangePasswordResponse',
                fields={
                    'status': serializers.CharField(),
                    'code': serializers.IntegerField(),
                    'message': serializers.CharField(),
                    'data': serializers.JSONField(),
                },
            ),
            400: OpenApiResponse(description="Ancien mot de passe incorrect ou données invalides."),
        },
    ),
    patch=extend_schema(
        tags=['Authentification'],
        operation_id='auth_change_password_partial',
        summary="Changer le mot de passe (partiel)",
        description="Variante PATCH du changement de mot de passe. "
                    "Authentification requise.",
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description="Mot de passe mis à jour."),
            400: OpenApiResponse(description="Ancien mot de passe incorrect ou données invalides."),
        },
    ),
)
class ChangePasswordView(generics.UpdateAPIView):
    """ use postman to test give 4 fields new_password  new_password_confirm email code post methode"""
    serializer_class = ChangePasswordSerializer
    model = User
    permission_classes = (IsAuthenticated,)

    def get_object(self, queryset=None):
        obj = self.request.user
        return obj

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Check old password
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response({"old_password": ["Wrong password."]}, status=status.HTTP_400_BAD_REQUEST)
            # set_password also hashes the password that the user will get
            self.object.set_password(serializer.data.get("new_password"))
            self.object.password_reset_count = 1
            self.object.save()
            response = {
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Password updated successfully',
                'data': []
            }

            return Response(response)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema_view(
    get=extend_schema(
        tags=['Utilisateurs & Profil'],
        operation_id='users_update_points',
        summary="Recalculer les points des utilisateurs",
        description="Recalcule et met à jour le score de points de tous les "
                    "utilisateurs à partir de leurs incidents, événements et "
                    "participations. Tâche de maintenance, endpoint public.",
        responses={
            200: inline_serializer(
                name='UpdatePointsResponse',
                fields={'status': serializers.CharField(), 'message': serializers.CharField()},
            ),
        },
    ),
)
class UpdatePointAPIListView(generics.CreateAPIView):
    permission_classes = (
    )
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get(self, request, format=None, **kwargs):
        users = User.objects.all()
        for user in users:
            incidents = Incident.objects.filter(user_id=user.id)
            evenements = Evenement.objects.filter(user_id=user.id)
            participate = Participate.objects.filter(user_id=user.id)
            user.points += (incidents.count()) + (evenements.count() * 2) + (participate.count())
            user.save()

        return Response({
            "status": "success",
            "message": "update success ",
        }, status=status.HTTP_200_OK)

@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetView(generics.CreateAPIView):
    """ use postman to test give 4 fields new_password  new_password_confirm email code post methode"""
    permission_classes = (

    )
    queryset = User.objects.all()
    serializer_class = ResetPasswordSerializer

    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_password_reset_confirm',
        summary="Confirmer la réinitialisation du mot de passe",
        description="Réinitialise le mot de passe à partir de l'email, du code "
                    "reçu et du nouveau mot de passe (confirmé). Le code expire "
                    "après ~1h. Endpoint public.",
        request=ResetPasswordSerializer,
        responses={
            201: inline_serializer(
                name='PasswordResetConfirmResponse',
                fields={'status': serializers.CharField(), 'message': serializers.CharField()},
            ),
            400: OpenApiResponse(description="Code/email manquant, mots de passe non "
                                             "concordants, code expiré ou introuvable."),
        },
    )
    def post(self, request, *args, **kwargs):
        print("✅ post() de PasswordResetView appelée")
        if 'code' not in request.data or request.data['code'] is None:
            return Response({
                "status": "failure",
                "message": "no code provided",
                "error": "not such item"
            }, status=status.HTTP_400_BAD_REQUEST)

        if 'email' not in request.data or request.data['email'] is None:
            return Response({
                "status": "failure",
                "message": "no email provided",
                "error": "not such item"
            }, status=status.HTTP_400_BAD_REQUEST)

        if 'new_password' not in request.data or 'new_password_confirm' not in request.data or request.data[
            'new_password'] is None or request.data['new_password'] != request.data['new_password_confirm']:
            return Response({
                "status": "failure",
                "message": "non matching passwords",
                "error": "not such item"
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            user_ = User.objects.get(email=request.data['email'])
            code_ = request.data['code']
            if user_ is None:
                return Response({
                    "status": "failure",
                    "message": "no such item",
                    "error": "not such item"
                }, status=status.HTTP_400_BAD_REQUEST)

            passReset = PasswordReset.objects.filter(
                user=user_, code=code_, used=False).order_by('-date_created').first()
            if passReset is None:
                return Response({
                    "status": "failure",
                    "message": "not such item",
                    "error": "not such item"
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check if the reset code has expired
            timeout_hours = getattr(settings, 'PASSWORD_RESET_TIMEOUT_HOURS', 1)
            expiry_time = passReset.date_created + timedelta(hours=timeout_hours)
            if timezone.now() > expiry_time:
                return Response({
                    "status": "failure",
                    "message": "reset code has expired",
                    "error": "expired code"
                }, status=status.HTTP_400_BAD_REQUEST)

            user_.set_password(request.data['new_password'])
            user_.save()
            passReset.used = True
            passReset.date_used = timezone.now()
            passReset.save()


        except User.DoesNotExist:
            return Response({
                "status": "failure",
                "message": "invalid data",
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "status": "success",
            "message": "item successfully saved",
        }, status=status.HTTP_201_CREATED)

class PasswordResetRequestView(generics.CreateAPIView):
    """ use postman to test give field email post methode"""
    permission_classes = (

    )
    queryset = User.objects.all()
    serializer_class = RequestPasswordSerializer

    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_password_reset_request',
        summary="Demander un code de réinitialisation",
        description="Génère un code de réinitialisation à 7 caractères (valide "
                    "~1h) et l'envoie par email à l'utilisateur. Endpoint public.",
        request=RequestPasswordSerializer,
        responses={
            201: inline_serializer(
                name='PasswordResetRequestResponse',
                fields={'status': serializers.CharField(), 'message': serializers.CharField()},
            ),
            400: OpenApiResponse(description="Email manquant ou utilisateur introuvable."),
        },
    )
    def post(self, request, *args, **kwargs):
        if 'email' not in request.data or request.data['email'] is None:
            return Response({
                "status": "failure",
                "message": "no email provided",
                "error": "not such item"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_ = User.objects.get(email=request.data['email'])
            code_ = get_random()
            PasswordReset.objects.create(
                user=user_,
                code=code_
            )
            subject = '[MAP ACTION] - Votre code de réinitialisation'
            from_email = 'Map Action <{}>'.format(settings.EMAIL_HOST_USER)  
            to = user_.email
            html_content = render_to_string('mail_pwd.html', {'code': code_})  # render with dynamic value#
            text_content = strip_tags(html_content)  # Strip the html tag. So people can see the pure text at least.
            msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
            msg.attach_alternative(html_content, "text/html")
            msg.send()

        except User.DoesNotExist:
            # print('sen error mail')
            return Response({
                "status": "failure",
                "message": "no such item",
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "status": "success",
            "message": "item successfully saved ",
        }, status=status.HTTP_201_CREATED)

class PhoneOTPView(generics.CreateAPIView):
    permission_classes = ()
    queryset = PhoneOTP.objects.all()
    serializer_class = PhoneOTPSerializer
    def generate_otp(self, phone_number):
        secret_key = pyotp.random_base32()
        otp = pyotp.TOTP(secret_key)
        otp_code = otp.now()
        otp_code_str = str(otp_code)
        PhoneOTP.objects.create(phone_number=phone_number, otp_code=otp_code_str)
        return otp_code_str
    
    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_phone_otp_get',
        summary="Récupérer le code OTP d'un numéro",
        description="Retourne le dernier code OTP enregistré pour le numéro de "
                    "téléphone fourni en paramètre de requête. Endpoint public.",
        parameters=[OpenApiParameter('phone_number', OpenApiTypes.STR,
                                     OpenApiParameter.QUERY, required=True,
                                     description="Numéro de téléphone")],
        request=None,
        responses={
            200: inline_serializer(
                name='PhoneOtpGetResponse',
                fields={'otp_code': serializers.CharField()},
            ),
            400: OpenApiResponse(description="Numéro de téléphone manquant."),
            404: OpenApiResponse(description="Aucun code OTP pour ce numéro."),
        },
    )
    def get(self, request, *args, **kwargs):
        phone_number = request.query_params.get('phone_number')
        if not phone_number:
            raise ValidationError("Le numéro de téléphone est requis.")
        try:
            otp_instance = PhoneOTP.objects.get(phone_number=phone_number)
        except PhoneOTP.DoesNotExist:
            raise NotFound("Code OTP non trouvé pour ce numéro de téléphone.")
        return Response({'otp_code': otp_instance.otp_code}, status=status.HTTP_200_OK)
    
    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_phone_otp_create',
        summary="Générer et envoyer un code OTP",
        description="Génère un code OTP pour le numéro fourni et l'envoie par "
                    "SMS (Orange Mali). Endpoint public.",
        request=PhoneOTPSerializer,
        responses={
            201: inline_serializer(
                name='PhoneOtpCreateResponse',
                fields={'otp_code': serializers.CharField()},
            ),
            400: OpenApiResponse(description="Numéro de téléphone manquant."),
            500: OpenApiResponse(description="Échec de l'envoi du SMS."),
        },
    )
    def post(self, request, *args, **kwargs):
        phone_number = request.data.get('phone_number')
        if not phone_number:
            raise ValidationError("Le numéro de téléphone est requis.")
        otp_code = self.generate_otp(phone_number)
        if send_sms(phone_number, otp_code):
            return Response({'otp_code': otp_code}, status=status.HTTP_201_CREATED)
        else:
            return Response({'message': 'Erreur lors de l\'envoi du SMS'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def send_sms(phone_number, otp_code):
    """Envoi du code OTP par SMS via Twilio (remplace l'ancienne API Orange Mali).

    Twilio est déjà utilisé pour l'IVR (cf. ivr_views.py) ; on réutilise les mêmes
    identifiants ``TWILIO_*``. Le numéro est normalisé en E.164 (+223 par défaut, Mali).
    """
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        recipient = phone_number if phone_number.startswith('+') else f"+223{phone_number.lstrip('0')}"

        message = client.messages.create(
            body=f"Votre code de vérification OTP est : {otp_code}",
            from_=settings.TWILIO_PHONE_NUMBER,
            to=recipient,
        )

        if message.sid:
            print(f"SMS OTP envoyé via Twilio. SID: {message.sid}")
            return True
        print("Erreur: pas de SID retourné par Twilio")
        return False
    except Exception as e:
        print(f"Erreur lors de l'envoi SMS Twilio: {str(e)}")
        return False
    

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer

    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_register_citizen',
        summary="Inscription citoyen (email)",
        description="Crée un compte à partir d'un email seul et envoie un lien "
                    "de vérification par email. Endpoint public.",
        request=RegisterSerializer,
        responses={
            201: inline_serializer(
                name='RegisterCitizenResponse',
                fields={'message': serializers.CharField()},
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({"message": "Un lien de vérification a été envoyé à votre adresse email."}, status=status.HTTP_201_CREATED)

class VerifyEmailView(APIView):
    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_verify_email',
        summary="Vérifier l'email",
        description="Valide l'adresse email associée au token de vérification "
                    "et marque l'utilisateur comme vérifié. Endpoint public.",
        parameters=[OpenApiParameter('token', OpenApiTypes.UUID, OpenApiParameter.PATH,
                                     description="Token de vérification")],
        request=None,
        responses={
            200: inline_serializer(
                name='VerifyEmailResponse',
                fields={'message': serializers.CharField()},
            ),
            400: OpenApiResponse(description="Lien de vérification invalide."),
        },
    )
    def get(self, request, token, *args, **kwargs):
        try:
            user = User.objects.get(verification_token=token)
            user.is_verified = True
            user.verification_token = None 
            user.save()
            return Response({"message": "Email vérifié avec succès !"}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "Lien de vérification invalide"}, status=status.HTTP_400_BAD_REQUEST)

@extend_schema_view(
    put=extend_schema(
        tags=['Authentification'],
        operation_id='auth_set_password',
        summary="Définir le mot de passe",
        description="Définit le mot de passe de l'utilisateur authentifié "
                    "(étape post-vérification). Authentification requise.",
        request=SetPasswordSerializer,
        responses={200: OpenApiResponse(description="Mot de passe défini.")},
    ),
    patch=extend_schema(
        tags=['Authentification'],
        operation_id='auth_set_password_partial',
        summary="Définir le mot de passe (partiel)",
        description="Variante PATCH pour définir le mot de passe de "
                    "l'utilisateur authentifié. Authentification requise.",
        request=SetPasswordSerializer,
        responses={200: OpenApiResponse(description="Mot de passe défini.")},
    ),
)
class SetPasswordView(generics.UpdateAPIView):
    serializer_class = SetPasswordSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
    

class RequestOTPView(APIView):
    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_otp_request',
        summary="Demander un OTP (téléphone)",
        description="Crée ou récupère l'utilisateur par numéro de téléphone, "
                    "génère un OTP et l'envoie par SMS. Endpoint public.",
        request=inline_serializer(
            name='RequestOtpRequest',
            fields={'phone': serializers.CharField()},
        ),
        responses={
            200: inline_serializer(
                name='RequestOtpResponse',
                fields={'message': serializers.CharField()},
            ),
            500: OpenApiResponse(description="Échec de l'envoi du SMS."),
        },
    )
    def post(self, request):
        phone = request.data.get("phone")
        user = User.objects.get_or_create_user(phone=phone)

        user.generate_otp()

        if send_sms(phone, user.otp):
            return Response({"message": "OTP envoyé."}, status=status.HTTP_200_OK)
        else:
            return Response({"message": "Erreur lors de l'envoi du SMS"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VerifyOTPView(APIView):
    @extend_schema(
        tags=['Authentification'],
        operation_id='auth_otp_verify',
        summary="Vérifier un OTP (téléphone)",
        description="Vérifie le couple téléphone/OTP ; si valide, retourne des "
                    "tokens JWT et les informations de l'utilisateur. Endpoint public.",
        request=inline_serializer(
            name='VerifyOtpRequest',
            fields={'phone': serializers.CharField(), 'otp': serializers.CharField()},
        ),
        responses={
            200: inline_serializer(
                name='VerifyOtpResponse',
                fields={
                    'refresh': serializers.CharField(),
                    'access': serializers.CharField(),
                    'user': inline_serializer(
                        name='VerifyOtpUser',
                        fields={
                            'id': serializers.UUIDField(),
                            'email': serializers.EmailField(),
                            'first_name': serializers.CharField(),
                            'last_name': serializers.CharField(),
                            'phone': serializers.CharField(),
                            'is_verified': serializers.BooleanField(),
                            'user_type': serializers.CharField(),
                        },
                    ),
                },
            ),
            400: OpenApiResponse(description="OTP invalide ou expiré."),
            404: OpenApiResponse(description="Utilisateur non trouvé."),
        },
    )
    def post(self, request):
        phone = request.data.get("phone")
        otp = request.data.get("otp")

        try:
            user = User.objects.get(phone=phone, otp=otp)
            if user.is_otp_valid():
                refresh = RefreshToken.for_user(user)

                user.otp = None
                user.save()

                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'user': {
                        'id' : user.id,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'phone': user.phone,
                        'is_verified': user.is_verified,
                        'user_type': user.user_type,
                    }
                }, status=status.HTTP_200_OK)
            else:
                return Response({"message": "OTP invalide ou expiré"}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({"message": "Utilisateur non trouvé"}, status=status.HTTP_404_NOT_FOUND)

