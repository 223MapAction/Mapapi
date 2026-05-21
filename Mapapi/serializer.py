from rest_framework import serializers, generics, permissions, status
from .models import *



from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework.serializers import ModelSerializer
from django.contrib.auth.hashers import make_password
from django.utils import timezone


class OrganisationSerializer(serializers.ModelSerializer):
    members_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Organisation
        fields = '__all__'

    def get_members_count(self, obj):
        return obj.members.count()


class OrganisationMemberSerializer(serializers.ModelSerializer):
    """Serializer pour la gestion des membres d'une organisation."""
    organisation_name = serializers.CharField(source='organisation_member.name', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone',
            'organisation_member', 'organisation_name', 'org_role',
            'agent_code', 'is_active', 'date_joined',
        ]
        read_only_fields = ('id', 'email', 'date_joined', 'agent_code')

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

 
class UserSerializer(ModelSerializer):
    incident_preferences = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False
    )
    organisation_name = serializers.CharField(
        source='organisation_member.name', read_only=True
    )

    class Meta:
        model = User
        exclude = ('user_permissions', 'is_superuser', 'is_active', 'is_staff')

    def create(self, validated_data):
        zones = validated_data.pop('zones', None)
        incident_preferences = validated_data.pop('incident_preferences', [])

        user = self.Meta.model(**validated_data)
        user.set_password(validated_data['password'])
        user.save()

        if zones:
            user.zones.set(zones)


        if user.user_type == "elu" and incident_preferences:
            for incident_type in incident_preferences:
                OrganisationTag.objects.create(user=user, incident_type=incident_type)

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
        read_only_fields = ('progress',)

    def validate(self, data):
        """Validation supplémentaire sur la clôture d'un incident.

        Un incident ne peut passer à l'état RESOLVED que si :
          - `resolution_start_date` ET `resolution_end_date` sont renseignées ;
          - toutes les tâches associées sont à l'état 'done'.
        """
        # on prend la nouvelle valeur d'etat si elle est fournie, sinon l'actuelle
        new_etat = data.get('etat', getattr(self.instance, 'etat', None))
        if new_etat == RESOLVED:
            start = data.get('resolution_start_date',
                             getattr(self.instance, 'resolution_start_date', None))
            end = data.get('resolution_end_date',
                           getattr(self.instance, 'resolution_end_date', None))
            if not start or not end:
                raise serializers.ValidationError(
                    "La clôture d'un incident exige resolution_start_date et resolution_end_date."
                )
            if start > end:
                raise serializers.ValidationError(
                    "resolution_start_date doit être antérieure ou égale à resolution_end_date."
                )
            # toutes les tâches doivent être terminées
            if self.instance is not None:
                open_tasks = self.instance.tasks.exclude(state__in=[TASK_DONE, TASK_FAILED])
                if open_tasks.exists():
                    raise serializers.ValidationError(
                        f"Impossible de clôturer : {open_tasks.count()} tâche(s) non terminée(s)."
                    )
        return data


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

class CollaborationSerializer(ModelSerializer):
    class Meta:
        model = Collaboration
        fields = '__all__'
        # 'status' et 'role' ne sont PAS settables librement par le demandeur :
        # - status est géré par le leader via les endpoints accept/decline
        # - role = 'leader' est auto-attribué quand une organisation prend l'incident ;
        #   une demande manuelle ne peut proposer que contributor/observer
        read_only_fields = ('status',)

    def validate_role(self, value):
        """Un utilisateur ne peut pas se déclarer leader lui-même.

        Le rôle leader est exclusivement attribué automatiquement à l'organisation
        qui prend l'incident en charge (Incident.taken_by).
        """
        if value == COLLAB_ROLE_LEADER:
            raise serializers.ValidationError(
                "Le rôle 'leader' ne peut pas être demandé manuellement. "
                "Il est attribué automatiquement lors de la prise en charge de l'incident."
            )
        return value

    def validate(self, data):
        # Valider la date de fin : doit être future si fournie
        if data.get('end_date') and data['end_date'] <= timezone.now().date():
            raise serializers.ValidationError("La date de fin doit être dans le futur")

        # On ne peut pas créer une collaboration sur un incident clôturé
        incident = data.get('incident') or getattr(self.instance, 'incident', None)
        if incident and incident.is_resolved:
            raise serializers.ValidationError(
                "Impossible d'ajouter une collaboration : l'incident est clôturé."
            )
        return data


class CollaborationEnrichedSerializer(ModelSerializer):
    """Serializer enrichi pour la vue collaboration dashboard."""
    organisation_name = serializers.SerializerMethodField()
    user_role = serializers.CharField(source='role', read_only=True)
    incident_title = serializers.CharField(source='incident.title', read_only=True)
    incident_description = serializers.CharField(source='incident.description', read_only=True)
    incident_zone = serializers.CharField(source='incident.zone', read_only=True)
    incident_etat = serializers.CharField(source='incident.etat', read_only=True)
    incident_progress = serializers.IntegerField(source='incident.progress', read_only=True)
    start_date = serializers.DateTimeField(source='created_at', read_only=True)
    participants_count = serializers.SerializerMethodField()

    class Meta:
        model = Collaboration
        fields = [
            'id', 'incident', 'user', 'status', 'role',
            'organisation_name', 'user_role',
            'incident_title', 'incident_description', 'incident_zone',
            'incident_etat', 'incident_progress',
            'start_date', 'end_date',
            'participants_count', 'motivation',
        ]

    def get_organisation_name(self, obj):
        if obj.user and obj.user.organisation_member:
            return obj.user.organisation_member.name
        return obj.user.organisation if obj.user else None

    def get_participants_count(self, obj):
        return Collaboration.objects.filter(
            incident=obj.incident, status='accepted'
        ).count()

class ColaborationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Colaboration
        fields = '__all__'

class PredictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prediction
        fields = '__all__'
        read_only_fields = (
            'status', 'macro_category', 'sub_category', 'description',
            'source_size_meters', 'spread_vectors',
            'impact_radius_meters', 'radius_explanation',
            'global_impact_score', 'base_severity', 'impact_tags',
            'recommendation',
            'latitude', 'longitude',
            'city', 'region', 'country', 'display_name',
            'social_vulnerability_score', 'is_social_probabilistic',
            'total_population_exposed', 'adult_men_exposed',
            'adult_women_exposed', 'children_exposed',
            'maternities_count', 'nurseries_count',
            'health_centers', 'maternities', 'schools', 'nurseries',
            'markets', 'water_points', 'main_roads_bridges',
            'residential_buildings',
            'ai_analysis', 'topography', 'satellite', 'social_data',
            'human_impact', 'geocoding', 'potential_risk', 'full_response',
            'error_message', 'created_at', 'updated_at',
        )

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


class IncidentAssignmentSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    agent_email = serializers.EmailField(source='agent.email', read_only=True)
    incident_title = serializers.CharField(source='incident.title', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.get_full_name', read_only=True)

    class Meta:
        model = IncidentAssignment
        fields = '__all__'
        read_only_fields = ('assigned_by', 'created_at', 'updated_at')

    def validate(self, data):
        agent = data.get('agent') or (self.instance.agent if self.instance else None)
        incident = data.get('incident') or (self.instance.incident if self.instance else None)
        deadline = data.get('deadline') or (self.instance.deadline if self.instance else None)

        if not deadline:
            raise serializers.ValidationError("La deadline est obligatoire.")

        if agent and agent.org_role != ORG_ROLE_FIELD:
            raise serializers.ValidationError("L'utilisateur assigné doit être un agent de terrain.")

        if agent and incident and agent.organisation_member:
            incident_owner_org = None
            if incident.user_id and incident.user_id.organisation_member:
                incident_owner_org = incident.user_id.organisation_member
            elif incident.taken_by and incident.taken_by.organisation_member:
                incident_owner_org = incident.taken_by.organisation_member

            if incident_owner_org and agent.organisation_member != incident_owner_org:
                raise serializers.ValidationError("L'agent doit appartenir à l'organisation liée à l'incident.")

        return data


class FieldReportSerializer(ModelSerializer):
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    incident_title = serializers.CharField(source='incident.title', read_only=True)
    incident_zone = serializers.CharField(source='incident.zone', read_only=True)

    class Meta:
        model = FieldReport
        fields = '__all__'
        read_only_fields = ('agent', 'incident', 'visited_at', 'created_at')

    def validate(self, data):
        request = self.context.get('request')
        agent = data.get('agent') or (self.instance.agent if self.instance else None) or (request.user if request else None)
        if agent and agent.org_role != ORG_ROLE_FIELD:
            raise serializers.ValidationError("Seuls les agents de terrain peuvent créer des rapports de déplacement.")

        incident = data.get('incident') or (self.instance.incident if self.instance else None)
        if incident:
            if agent and not IncidentAssignment.objects.filter(incident=incident, agent=agent).exists():
                raise serializers.ValidationError("Vous ne pouvez créer un rapport que pour un incident qui vous est assigné.")

            try:
                import math
                inc_lat = float(incident.lattitude) if incident.lattitude else None
                inc_lon = float(incident.longitude) if incident.longitude else None

                agent_lat = float(data.get('location_lat')) if data.get('location_lat') else None
                agent_lon = float(data.get('location_lon')) if data.get('location_lon') else None

                if all([inc_lat, inc_lon, agent_lat, agent_lon]):
                    lat1, lon1, lat2, lon2 = map(math.radians, [inc_lat, inc_lon, agent_lat, agent_lon])
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                    c = 2 * math.asin(math.sqrt(a))
                    distance_km = 6371 * c  # Rayon de la Terre en km
                    distance_meters = distance_km * 1000

                    # Validation : l'agent doit être à moins de 100m de l'incident
                    if distance_meters > 100:
                        raise serializers.ValidationError(
                            f"Vous devez être sur le lieu de l'incident (distance calculée: {distance_meters:.0f}m)."
                        )

                    data['distance_meters'] = distance_meters
            except (ValueError, TypeError):
                # Si les coordonnées ne sont pas disponibles, on ne peut pas valider la distance
                pass

        return data


class DiscussionMessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    recipient = UserSerializer(read_only=True)

    class Meta:
        model = DiscussionMessage
        fields = ['id', 'incident', 'collaboration', 'sender',
                  'message', 'audio', 'attachment',
                  'created_at', 'recipient']
        read_only_fields = ('sender', 'incident', 'collaboration', 'recipient')

    def validate(self, data):
        """Un message doit contenir au moins un payload : texte, audio ou pièce jointe."""
        message = data.get('message') or (self.instance.message if self.instance else None)
        audio = data.get('audio') or (self.instance.audio if self.instance else None)
        attachment = data.get('attachment') or (self.instance.attachment if self.instance else None)
        if not message and not audio and not attachment:
            raise serializers.ValidationError(
                "Un message doit contenir du texte, un audio ou une pièce jointe."
            )
        return data


class IncidentTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentTask
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')

    def validate(self, data):
        # Refus d'ajouter/modifier une tâche sur un incident clôturé
        incident = data.get('incident') or getattr(self.instance, 'incident', None)
        if incident and incident.is_resolved:
            raise serializers.ValidationError(
                "Impossible de modifier les tâches d'un incident clôturé."
            )

        start = data.get('start_date', getattr(self.instance, 'start_date', None))
        end = data.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and start > end:
            raise serializers.ValidationError(
                "start_date doit être antérieure ou égale à end_date."
            )

        # Validations conditionnelles sur l'état final
        state = data.get('state', getattr(self.instance, 'state', TASK_PENDING))
        proof_image = data.get('proof_image', getattr(self.instance, 'proof_image', None))
        proof_video = data.get('proof_video', getattr(self.instance, 'proof_video', None))
        failure_reason = data.get('failure_reason', getattr(self.instance, 'failure_reason', None))

        if state == TASK_DONE and not (proof_image or proof_video):
            raise serializers.ValidationError(
                "Une tâche marquée 'done' doit fournir une preuve (image ou vidéo)."
            )
        if state == TASK_FAILED and not failure_reason:
            raise serializers.ValidationError(
                "Une tâche marquée 'failed' doit inclure un motif (failure_reason)."
            )
        return data


class PartnerSuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerSuggestion
        fields = '__all__'
        read_only_fields = ('suggested_by', 'status', 'created_at', 'updated_at')

    def validate(self, data):
        incident = data.get('incident') or getattr(self.instance, 'incident', None)
        if incident and incident.is_resolved:
            raise serializers.ValidationError(
                "Impossible de suggérer un partenaire sur un incident clôturé."
            )

        suggested_partner = data.get('suggested_partner') or getattr(
            self.instance, 'suggested_partner', None)
        if incident and suggested_partner:
            # refuser si l'organisation est déjà collaboratrice acceptée
            already = Collaboration.objects.filter(
                incident=incident, user=suggested_partner, status='accepted'
            ).exists()
            if already:
                raise serializers.ValidationError(
                    "Cette organisation collabore déjà sur l'incident."
                )
        return data


