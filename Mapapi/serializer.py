from rest_framework import serializers, generics, permissions, status
from .models import *
from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework.serializers import ModelSerializer
from django.contrib.auth.hashers import make_password


class UserSerializer(ModelSerializer):
    class Meta:
        model = User
        exclude = (
            'user_permissions', 'is_superuser', 'is_active', 'is_staff')

    def create(self, validated_data):
        zones = validated_data.pop('zones', None)
        user = self.Meta.model(**validated_data)
        user.set_password(validated_data['password'])
        user.save()
        if zones:
            user.zones.set(zones)
        return user


class UserRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'
        depth = 1

    def create(self, validated_data):
        user = User(
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=validated_data['phone'],
            is_active=True,
            address=validated_data['address']
        )
        user.set_password(validated_data['password'])
        user.save()
        return user


class UserEluSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        exclude = (
            'user_permissions', 'is_superuser', 'is_active', 'is_staff', 'password')

    def create(self, validated_data, **extra_fields):
        user = self.Meta.model(**validated_data)
        user.active = True
        user.user_type = "elu"
        user.save()
        return user


class UserPutSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'


class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email']

    def create(self, validated_data):
        user = User.objects.create(**validated_data)
        user.send_verification_email()
        return user


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        return value

    def save(self, user):
        user.set_password(self.validated_data['password'])
        user.save()


class CategorySerializer(ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class IncidentSerializer(ModelSerializer):
    class Meta:
        model = Incident
        fields = '__all__'


class IncidentGetSerializer(ModelSerializer):
    user_id = UserSerializer()
    category_id = CategorySerializer()

    class Meta:
        model = Incident
        fields = '__all__'


class EvenementSerializer(ModelSerializer):
    class Meta:
        model = Evenement
        fields = '__all__'


class ContactSerializer(ModelSerializer):
    class Meta:
        model = Contact
        fields = '__all__'


class CommunauteSerializer(ModelSerializer):
    class Meta:
        model = Communaute
        fields = '__all__'


class RapportSerializer(ModelSerializer):
    class Meta:
        model = Rapport
        fields = '__all__'


class RapportGetSerializer(ModelSerializer):
    user_id = UserSerializer()

    class Meta:
        model = Rapport
        fields = '__all__'


class ParticipateSerializer(ModelSerializer):
    class Meta:
        model = Participate
        fields = '__all__'


class ZoneSerializer(ModelSerializer):
    class Meta:
        model = Zone
        fields = '__all__'


class MessageSerializer(ModelSerializer):
    class Meta:
        model = Message
        fields = '__all__'


class MessageGetSerializer(ModelSerializer):
    user_id = UserSerializer()
    communaute = CommunauteSerializer()
    zone = ZoneSerializer()

    class Meta:
        model = Message
        fields = '__all__'


class MessageByZoneSerializer(ModelSerializer):
    user_id = UserSerializer()

    class Meta:
        model = Message
        fields = '__all__'


class ResponseMessageSerializer(ModelSerializer):
    class Meta:
        model = ResponseMessage
        fields = '__all__'


class IndicateurSerializer(ModelSerializer):
    class Meta:
        model = Indicateur
        fields = '__all__'


class ChangePasswordSerializer(serializers.Serializer):
    model = User

    """
    Serializer for password change endpoint.
    """
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


class RequestPasswordSerializer(serializers.Serializer):
    model = User

    """
    Serializer for password change endpoint.
    """
    email = serializers.CharField(required=True)


class ResetPasswordSerializer(serializers.Serializer):
    model = User

    """
    Serializer for password change endpoint.
    """
    code = serializers.CharField(required=True)
    email = serializers.CharField(required=True)
    new_password_confirm = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


class ImageBackgroundSerializer(ModelSerializer):
    class Meta:
        model = ImageBackground
        fields = '__all__'


class EluToZoneSerializer(serializers.Serializer):
    elu = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(user_type='elu'))
    zone = serializers.PrimaryKeyRelatedField(queryset=Zone.objects.all())

    def create(self, validated_data):
        elu = validated_data.pop('elu')
        zone = validated_data.pop('zone')
        # Directly use the instances
        elu.zones.add(zone)
        elu.save()
        return {
            'elu': elu,
            'zone': zone
        }


class PhoneOTPSerializer(serializers.ModelSerializer):
    class Meta:
        model = PhoneOTP
        fields = ['phone_number']

class CollaborationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collaboration
        fields = '__all__'

class ColaborationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Colaboration
        fields = '__all__'

class PredictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prediction
        fields = '__all__'

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'


class ChatHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatHistory
        fields = '__all__'


class UserActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAction
        fields = '__all__' 


class DiscussionMessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    recipient = UserSerializer(read_only=True)
    class Meta:
        model = DiscussionMessage
        fields = ['id', 'incident', 'collaboration', 'sender', 'message', 'created_at','recipient']
        read_only_fields = ('sender', 'incident', 'collaboration','recipient')


