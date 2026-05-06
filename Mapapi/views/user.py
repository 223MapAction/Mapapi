"""User & authentication endpoints (register, login, password reset, OTP, profile)."""
import os
import time
from datetime import timedelta

import pyotp
from twilio.rest import Client

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import strip_tags
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from ..serializer import *
from ..Send_mails import send_email
from .common import CustomPageNumberPagination, get_random, logger


@extend_schema(
    description="Endpoint for retrieval token by email",
    request=UserSerializer,
    responses={201: UserSerializer, 400: "Bad request"}
)
class GetTokenByMailView(generics.CreateAPIView):
    permission_classes = ()
    queryset = User.objects.all()
    serializer_class = UserSerializer
    
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

@api_view(['GET', 'POST'])
@extend_schema(
    description="Endpoint allowing retrieval and creation of users. Retrieves all users from the database and register a new user",
    request=UserSerializer,
    responses={201: UserSerializer, 400: "Bad request"},
    parameters=[
        OpenApiParameter(name='first_name', description='First name of the user', required=True, type=str),
        OpenApiParameter(name='last_name', description='Last name of the user', required=True, type=str),
        OpenApiParameter(name='phone', description='Phone number of the user', required=False, type=str),
        OpenApiParameter(name='address', description='Address of the user', required=False, type=str),
        OpenApiParameter(name='email', description='Email of the user', required=True, type=str),
        OpenApiParameter(name='password', description='Password of the user', required=True, type=str),
    ],
    examples=[
        OpenApiExample(name='User', value={
            'first_name': 'Annoura',
            'last_name': 'Toure',
            'phone': '20303020',
            'address': 'Mali',
            'email': 'john@example.com',
            'password': 'secret_password'
        })
    ]
)
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

@api_view(['GET', 'PUT', 'DELETE'])
@extend_schema(
    description="Endpoint allowing retrieval, updating, and deletion of an user.",
    request=UserSerializer,
    responses={200: UserSerializer, 404: "user not found"},  
)
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
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@extend_schema(
    description="Endpoint allowing retrieval and creation of users. Retrieves all users from the database, "
                "sorts them by primary identifier, paginates the results, and serializes them before returning "
                "the paginated response to the client. For creation, deserializes the request data and saves it "
                "to the database. Additionally, sends emails to users based on the type of account created.",
    request=UserSerializer,
    responses={201: UserSerializer, 400: "Bad request"}, 
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

@extend_schema(
    description="Endpoint allowing retrivial of citizen.",
    responses={200: UserSerializer, 404: "Citizen not found"},  
)
class CitizenAPIListView(generics.ListAPIView):
    permission_classes = ()
    queryset = User.objects.filter(user_type='citizen').order_by('pk')
    serializer_class = UserSerializer
    pagination_class = PageNumberPagination

    def get(self, request, *args, **kwargs):
        self.pagination_class.page_size = 10  # Modifier ici pour définir la taille de la page
        return self.list(request, *args, **kwargs)

@extend_schema(
    description="Endpoint allowing retrival of user.",
    responses={200: UserSerializer, 404: "User not found"},  
)
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

@extend_schema(
    description="Endpoint for changing password",
    responses={200: ChangePasswordSerializer, 400: "bad request"}
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

@extend_schema(
    description="Endpoint for updating points of users based on their activities.",
    responses={200: "Points updated successfully."},
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

@extend_schema(
    description="Endpoint for resetting user password.",
    request=ResetPasswordSerializer,
    responses={400: "Bad Request"},
)
class PasswordResetRequestView(generics.CreateAPIView):
    """ use postman to test give field email post methode"""
    permission_classes = (

    )
    queryset = User.objects.all()
    serializer_class = RequestPasswordSerializer

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
    @extend_schema(
        description="Endpoint for generate otp code",
        responses={200: "generate", 400: "Bad request"},
    )
    def generate_otp(self, phone_number):
        secret_key = pyotp.random_base32()
        otp = pyotp.TOTP(secret_key)
        otp_code = otp.now()
        otp_code_str = str(otp_code)
        PhoneOTP.objects.create(phone_number=phone_number, otp_code=otp_code_str)
        return otp_code_str
    
    @extend_schema(
        description="Endpoint for retrivial a code otp",
        request=PhoneOTPSerializer,
        responses={200: PhoneOTPSerializer, 404: "Not Found"},
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
        description="Endpoint for creating a code otp",
        request=PhoneOTPSerializer,
        responses={201: PhoneOTPSerializer, 400: "Bad request"},
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
    account_sid = os.environ['TWILIO_ACCOUNT_SID']
    auth_token = os.environ['TWILIO_AUTH_TOKEN']
    twilio_phone = os.environ['TWILIO_PHONE_NUMBER']

    client = Client(account_sid, auth_token)

    message_body = f"Votre code de vérification OTP est : {otp_code}"
    message = client.messages.create(
        body=message_body,
        from_=twilio_phone,
        to=phone_number
    )
    if message.sid:
        return True
    else:
        return False
    

@extend_schema(
    description="Endpoint to get user who took incident into account",
    responses={200: RegisterSerializer()},
)
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({"message": "Un lien de vérification a été envoyé à votre adresse email."}, status=status.HTTP_201_CREATED)

class VerifyEmailView(APIView):
    def get(self, request, token, *args, **kwargs):
        try:
            user = User.objects.get(verification_token=token)
            user.is_verified = True
            user.verification_token = None 
            user.save()
            return Response({"message": "Email vérifié avec succès !"}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "Lien de vérification invalide"}, status=status.HTTP_400_BAD_REQUEST)

class SetPasswordView(generics.UpdateAPIView):
    serializer_class = SetPasswordSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
    

class RequestOTPView(APIView):
    def post(self, request):
        phone = request.data.get("phone")
        user = User.objects.get_or_create_user(phone=phone)

        user.generate_otp()

        account_sid = os.environ['TWILIO_ACCOUNT_SID']
        auth_token = os.environ['TWILIO_AUTH_TOKEN']
        twilio_phone = os.environ['TWILIO_PHONE_NUMBER']

        client = Client(account_sid, auth_token)

        message = client.messages.create(
            body=f"Votre code de vérification est {user.otp}",
            from_=twilio_phone,
            to=phone
        )

        return Response({"message": "OTP envoyé."}, status=status.HTTP_200_OK)

class VerifyOTPView(APIView):
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

