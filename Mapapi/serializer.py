from rest_framework import serializers, generics, permissions, status
from .models import *



from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework.serializers import ModelSerializer
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
import base64
import uuid as _uuid
from django.core.files.base import ContentFile


class AvatarField(serializers.ImageField):
    """Champ avatar tolérant : accepte un fichier multipart OU une data-URL base64
    (le front lit le fichier en base64 via FileReader). Toute autre valeur (l'URL
    existante renvoyée par le front quand l'avatar n'a pas changé, chaîne, vide) est
    ignorée → l'avatar courant est conservé, plus de 400 « not a file »."""

    def to_internal_value(self, data):
        if hasattr(data, 'read'):  # fichier multipart classique
            return super().to_internal_value(data)
        if isinstance(data, str) and data.startswith('data:image'):
            try:
                header, b64 = data.split(';base64,', 1)
                ext = (header.split('/')[-1] or 'png')[:5]
                decoded = base64.b64decode(b64)
                f = ContentFile(decoded, name=f"avatar_{_uuid.uuid4().hex[:10]}.{ext}")
                return super().to_internal_value(f)
            except Exception:
                self.fail('invalid_image')
        raise serializers.SkipField()  # rien de nouveau à enregistrer


class OrganisationSerializer(serializers.ModelSerializer):
    members_count = serializers.SerializerMethodField(read_only=True)
    incidents_taken_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Organisation
        fields = '__all__'

    def get_members_count(self, obj) -> int:
        return obj.members.count()

    def get_incidents_taken_count(self, obj) -> int:
        # Incidents « pris en compte » par l'org = incidents dont le leader (taken_by)
        # est un membre de l'organisation. Exclut les incidents supprimés.
        return Incident.objects.filter(
            taken_by__organisation_member=obj, is_deleted=False
        ).count()


class OrganisationMemberSerializer(serializers.ModelSerializer):
    """Serializer pour la gestion des membres d'une organisation."""
    organisation_name = serializers.CharField(source='organisation_member.name', read_only=True)
    # Rôle web canonique (cf. roles.py) — même source que partout ailleurs, pour
    # qu'un objet user expose TOUJOURS le rôle de la même façon (pas de confusion
    # org_role vs user_type côté frontend).
    web_role = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone', 'avatar',
            'organisation_member', 'organisation_name', 'org_role', 'web_role',
            'agent_code', 'is_active', 'date_joined',
        ]
        read_only_fields = ('id', 'email', 'date_joined', 'agent_code', 'avatar')

    @extend_schema_field(serializers.ChoiceField(
        choices=['super_admin', 'org_admin', 'bureau_agent', 'field_agent'],
        allow_null=True,
        help_text="Rôle canonique du dashboard : super_admin si is_superuser, "
                  "sinon l'org_role (org_admin/bureau_agent/field_agent), sinon null. "
                  "Distinct de user_type (catégorie de compte).",
    ))
    def get_web_role(self, obj) -> str | None:
        from .roles import get_web_role
        return get_web_role(obj)

# Secrets d'authentification jamais exposés en lecture par l'API.
# Ceux-ci sont EXCLUS de la sortie (ni lus ni écrits via ces serializers).
SENSITIVE_USER_FIELDS = (
    'otp', 'otp_expiration', 'verification_token', 'pin_code',
)
# password : accepté en entrée (création/MAJ via set_password) mais jamais renvoyé.
PASSWORD_WRITE_ONLY = {'password': {'write_only': True}}


class UserRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        exclude = SENSITIVE_USER_FIELDS
        depth = 1
        extra_kwargs = PASSWORD_WRITE_ONLY

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
    avatar = AvatarField(required=False)
    incident_preferences = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False
    )
    organisation_name = serializers.CharField(
        source='organisation_member.name', read_only=True
    )
    web_role = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        exclude = ('user_permissions', 'is_superuser', 'is_active', 'is_staff') \
            + SENSITIVE_USER_FIELDS
        # password reste accepté en entrée (create() appelle set_password) mais
        # n'est jamais renvoyé.
        extra_kwargs = PASSWORD_WRITE_ONLY

    @extend_schema_field(serializers.ChoiceField(
        choices=['super_admin', 'org_admin', 'bureau_agent', 'field_agent'],
        allow_null=True,
        help_text="Rôle canonique du dashboard : super_admin si is_superuser, "
                  "sinon l'org_role (org_admin/bureau_agent/field_agent), sinon null. "
                  "Distinct de user_type (catégorie de compte).",
    ))
    def get_web_role(self, obj) -> str | None:
        from .roles import get_web_role
        return get_web_role(obj)

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
    avatar = AvatarField(required=False)

    class Meta:
        model = User
        exclude = SENSITIVE_USER_FIELDS
        extra_kwargs = PASSWORD_WRITE_ONLY


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


class IncidentActingOrgsMixin(serializers.Serializer):
    """Champs explicites partagés liste + détail (cf. services.incident_orgs) :
    qui a pris l'incident en charge, et toutes les organisations actives dessus.
    Permet à une autre organisation de voir, AVANT d'ouvrir l'incident, quelle(s)
    organisation(s) agissent déjà."""
    taken_by_organisation = serializers.SerializerMethodField(read_only=True)
    taken_by_name = serializers.SerializerMethodField(read_only=True)
    acting_organisations = serializers.SerializerMethodField(read_only=True)
    my_collaboration = serializers.SerializerMethodField(read_only=True)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_taken_by_organisation(self, obj):
        from .services.incident_orgs import taken_by_organisation
        return taken_by_organisation(obj)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_my_collaboration(self, obj):
        """Pour le viewer connecté : SA demande de collaboration sur cet incident
        (ou celle de SON organisation), QUEL QUE SOIT le statut — notamment
        ``pending``. Permet, dans la liste, de voir « j'ai demandé à collaborer,
        en attente » sur un incident déjà pris en charge par une autre org.
        Renvoie ``None`` si aucune demande (ou pas de viewer authentifié).
        Calculé sur ``collaboration_set`` préchargé → pas de N+1 en liste."""
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return None
        org_id = getattr(user, 'organisation_member_id', None)
        mine = []
        for c in obj.collaboration_set.all():
            cu = getattr(c, 'user', None)
            if not cu:
                continue
            if org_id is not None:
                if getattr(cu, 'organisation_member_id', None) == org_id:
                    mine.append(c)
            elif cu.id == user.id:
                mine.append(c)
        if not mine:
            return None
        # On garde la plus pertinente : accepted > pending > declined, puis récente.
        rank = {'accepted': 0, 'pending': 1, 'declined': 2}
        mine.sort(key=lambda c: (
            rank.get(c.status, 9),
            -(c.created_at.timestamp() if getattr(c, 'created_at', None) else 0),
        ))
        best = mine[0]
        org = getattr(getattr(best, 'user', None), 'organisation_member', None)
        return {
            'id': best.id,
            'status': best.status,
            'role': best.role,
            'created_at': best.created_at.isoformat() if getattr(best, 'created_at', None) else None,
            'organisation_id': org.id if org else None,
            'organisation_name': org.name if org else None,
        }

    def get_taken_by_name(self, obj) -> str | None:
        tb = getattr(obj, 'taken_by', None)
        if not tb:
            return None
        return f"{tb.first_name or ''} {tb.last_name or ''}".strip() or tb.email

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_acting_organisations(self, obj):
        from .services.incident_orgs import acting_organisations
        return acting_organisations(obj)


class IncidentOrgAssignmentNestedSerializer(serializers.ModelSerializer):
    """Lecture seule : assignations org exposées sur le détail d'un incident,
    pour que le front affiche les actions accepter/refuser (spec §2/§3)."""
    organisation_id = serializers.IntegerField(source='organisation.id', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True)

    class Meta:
        model = IncidentOrgAssignment
        fields = ('id', 'organisation_id', 'organisation_name', 'status', 'deadline')
        read_only_fields = fields


class IncidentSerializer(IncidentActingOrgsMixin, ModelSerializer):
    org_assignments = IncidentOrgAssignmentNestedSerializer(many=True, read_only=True)

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


class IncidentGetSerializer(IncidentActingOrgsMixin, ModelSerializer):
    user_id = UserSerializer()
    category_id = CategorySerializer()
    org_assignments = IncidentOrgAssignmentNestedSerializer(many=True, read_only=True)

    class Meta:
        model = Incident
        fields = '__all__'


class IncidentMapSerializer(ModelSerializer):
    """Sérialiseur ultra-léger pour la carte du dashboard.

    N'expose que les champs scalaires dont les marqueurs ont besoin. Il évite
    volontairement le M2M `category_ids`, le nested `org_assignments` et les URLs
    de fichiers (photo/video/audio) qui, via `IncidentSerializer(__all__)`,
    déclenchaient un N+1 (~126 requêtes pour 59 incidents → ~12 s sur le pooler
    Supabase distant). `taken_by` reste un PK (optimisation PK-only de DRF, pas de
    requête supplémentaire), donc l'endpoint ne fait plus qu'UNE requête. Les
    détails (photo, description, participants…) sont chargés à la demande via
    `GET /incident/<id>` quand un marqueur est cliqué."""

    class Meta:
        model = Incident
        fields = (
            'id', 'title', 'lattitude', 'longitude', 'etat', 'taken_by',
            'is_deleted', 'severity', 'created_at',
        )


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


class IncidentReportSerializer(ModelSerializer):
    """Rapport d'un agent vu depuis un incident (page Mes interventions / détail
    collaboration). Expose explicitement l'auteur + son organisation."""
    author = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Rapport
        fields = (
            'id', 'details', 'type', 'statut', 'date_livraison', 'disponible',
            'file', 'created_at', 'incident', 'author',
        )

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_author(self, obj):
        return _person_brief(obj.user_id)


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

def _person_brief(user):
    """Représentation explicite et minimale d'une personne + son organisation."""
    if not user:
        return None
    org = getattr(user, 'organisation_member', None)
    return {
        'id': user.id,
        'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email,
        'email': user.email,
        'organisation_id': org.id if org else None,
        'organisation_name': org.name if org else (getattr(user, 'organisation', None) or None),
    }


class CollaborationPartiesMixin(serializers.Serializer):
    """Expose EXPLICITEMENT l'émetteur et le récepteur d'une demande de
    collaboration, pour lever la confusion côté frontend (#8) :
    - sender (émetteur)  = l'organisation qui DEMANDE à rejoindre (collaboration.user)
    - receiver (récepteur) = le leader qui REÇOIT la demande (incident.taken_by)
    """
    sender = serializers.SerializerMethodField(read_only=True)
    receiver = serializers.SerializerMethodField(read_only=True)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_sender(self, obj):
        return _person_brief(getattr(obj, 'user', None))

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_receiver(self, obj):
        incident = getattr(obj, 'incident', None)
        return _person_brief(getattr(incident, 'taken_by', None)) if incident else None


class CollaborationSerializer(CollaborationPartiesMixin, ModelSerializer):
    # Nom de l'organisation du collaborateur (lecture seule)
    organisation_name = serializers.CharField(
        source='user.organisation_member.name', read_only=True, default=None
    )
    organisation_id = serializers.UUIDField(
        source='user.organisation_member_id', read_only=True, default=None
    )
    user_full_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source='user.email', read_only=True)
    incident_title = serializers.CharField(source='incident.title', read_only=True)
    # Raccourcis photo/miniature (en plus de incident_details) pour les cartes.
    incident_photo = serializers.ImageField(source='incident.photo', read_only=True)
    incident_thumbnail = serializers.ImageField(source='incident.thumbnail', read_only=True)
    incident_details = IncidentSerializer(source='incident', read_only=True)
    prediction_details = PredictionSerializer(source='incident.prediction', read_only=True)

    class Meta:
        model = Collaboration
        fields = '__all__'
        # 'status', 'user' et 'role'(leader) ne sont PAS settables librement par le demandeur :
        # - user = l'émetteur, TOUJOURS forcé à request.user dans la vue (le client
        #   n'envoie rien ; évite le 400 "Invalid pk" quand le FE postait un mauvais id)
        # - status est géré par le leader via les endpoints accept/decline
        # - role = 'leader' est auto-attribué quand une organisation prend l'incident ;
        #   une demande manuelle ne peut proposer que contributor/observer
        read_only_fields = ('status', 'user')

    def get_user_full_name(self, obj) -> str | None:
        if obj.user:
            return f"{obj.user.first_name or ''} {obj.user.last_name or ''}".strip() or obj.user.email
        return None

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


class CollaborationEnrichedSerializer(CollaborationPartiesMixin, ModelSerializer):
    """Serializer enrichi pour la vue collaboration dashboard."""
    organisation_name = serializers.SerializerMethodField()
    user_role = serializers.CharField(source='role', read_only=True)
    incident_title = serializers.CharField(source='incident.title', read_only=True)
    incident_description = serializers.CharField(source='incident.description', read_only=True)
    incident_zone = serializers.CharField(source='incident.zone', read_only=True)
    incident_etat = serializers.CharField(source='incident.etat', read_only=True)
    incident_progress = serializers.IntegerField(source='incident.progress', read_only=True)
    # Photo (+ miniature) de l'incident pour les cartes « Mes collaborations ».
    incident_photo = serializers.ImageField(source='incident.photo', read_only=True)
    incident_thumbnail = serializers.ImageField(source='incident.thumbnail', read_only=True)
    start_date = serializers.DateTimeField(source='created_at', read_only=True)
    participants_count = serializers.SerializerMethodField()

    class Meta:
        model = Collaboration
        fields = [
            'id', 'incident', 'user', 'status', 'role',
            'organisation_name', 'user_role', 'sender', 'receiver',
            'incident_title', 'incident_description', 'incident_zone',
            'incident_etat', 'incident_progress',
            'incident_photo', 'incident_thumbnail',
            'start_date', 'end_date',
            'participants_count', 'motivation',
        ]

    def get_organisation_name(self, obj) -> str | None:
        if obj.user and obj.user.organisation_member:
            return obj.user.organisation_member.name
        return obj.user.organisation if obj.user else None

    def get_participants_count(self, obj) -> int:
        return Collaboration.objects.filter(
            incident=obj.incident, status='accepted'
        ).count()

class ColaborationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Colaboration
        fields = '__all__'


class NotificationSerializer(serializers.ModelSerializer):
    link = serializers.SerializerMethodField(read_only=True)
    # `type` = catégorie (collaboration_request, incident_assignment, …) pour le
    # front (icône/logique) ; `title` = libellé FR prêt à afficher (plus de titre en
    # dur côté front). cf. incident_title pour le titre de l'incident concerné.
    type = serializers.CharField(source='notif_type', read_only=True)
    title = serializers.CharField(read_only=True)
    incident_title = serializers.CharField(source='incident.title', read_only=True, default=None)

    class Meta:
        model = Notification
        fields = '__all__'

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_link(self, obj):
        # Cible de redirection au clic ({type, incident_id, [collaboration_id], url}) ou null.
        return obj.redirect_link()


class ChatHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatHistory
        fields = '__all__'


class UserActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAction
        fields = '__all__'


class ActivityFeedSerializer(serializers.ModelSerializer):
    """Élément du flux d'activité : action + acteur + organisation + horodatage précis."""
    user_name = serializers.SerializerMethodField(read_only=True)
    organisation_name = serializers.SerializerMethodField(read_only=True)
    # `actor` = ce qu'on AFFICHE en tête de l'élément : le nom de l'ORGANISATION
    # (l'activité est au niveau org), avec repli sur le nom de la personne si elle
    # n'a pas d'organisation (ex. super admin). À utiliser à la place de `user_name`.
    actor = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = UserAction
        fields = ['id', 'action', 'timeStamp', 'created_at', 'user', 'user_name', 'organisation_name', 'actor']

    def get_user_name(self, obj) -> str | None:
        u = obj.user
        if not u:
            return None
        return (f"{u.first_name or ''} {u.last_name or ''}".strip()) or u.email

    def get_organisation_name(self, obj) -> str | None:
        u = obj.user
        return getattr(getattr(u, 'organisation_member', None), 'name', None) if u else None

    def get_actor(self, obj) -> str | None:
        return self.get_organisation_name(obj) or self.get_user_name(obj)


class IncidentAssignmentSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    agent_email = serializers.EmailField(source='agent.email', read_only=True)
    agent_phone = serializers.CharField(source='agent.phone', read_only=True)
    incident_title = serializers.CharField(source='incident.title', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.get_full_name', read_only=True)
    assigned_by_email = serializers.EmailField(source='assigned_by.email', read_only=True)
    # Détails complets de l'incident (lecture seule) pour que l'agent voie tout
    incident_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = IncidentAssignment
        fields = '__all__'
        read_only_fields = ('assigned_by', 'created_at', 'updated_at')

    @extend_schema_field(IncidentGetSerializer)
    def get_incident_detail(self, obj):
        if not obj.incident:
            return None
        return IncidentGetSerializer(obj.incident, context=self.context).data

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


class IncidentOrgAssignmentSerializer(serializers.ModelSerializer):
    """Assignation d'un incident à une organisation par le Super Admin (spec §2/§3)."""
    organisation_name = serializers.CharField(source='organisation.name', read_only=True)
    incident_title = serializers.CharField(source='incident.title', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.get_full_name', read_only=True)
    assigned_by_email = serializers.EmailField(source='assigned_by.email', read_only=True)

    class Meta:
        model = IncidentOrgAssignment
        fields = '__all__'
        read_only_fields = (
            'status', 'decline_reason', 'deadline', 'assigned_by',
            'created_at', 'responded_at',
        )


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
        # `incident` est TOUJOURS injecté depuis l'URL par la vue
        # (perform_create → serializer.save(incident=...)). Il ne doit donc pas être
        # exigé/envoyé dans le corps (sinon is_valid() échoue « This field may not be
        # null »). `created_by` est de même posé par la vue.
        read_only_fields = ('incident', 'created_by', 'created_at', 'updated_at', 'is_confirmed')

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
    incident_title = serializers.CharField(source='incident.title', read_only=True)
    suggested_by_name = serializers.SerializerMethodField()
    suggested_by_organisation = serializers.CharField(
        source='suggested_by.organisation_member.name', read_only=True, default=None
    )
    suggested_partner_name = serializers.SerializerMethodField()
    suggested_partner_organisation = serializers.CharField(
        source='suggested_partner.organisation_member.name', read_only=True, default=None
    )
    # Alternative côté front : envoyer l'ID d'organisation au lieu d'un user.
    # Le serializer résout automatiquement l'admin (ou à défaut le bureau_agent) de l'org.
    suggested_organisation = serializers.PrimaryKeyRelatedField(
        queryset=Organisation.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = PartnerSuggestion
        fields = '__all__'
        read_only_fields = ('suggested_by', 'status', 'created_at', 'updated_at')
        extra_kwargs = {
            # suggested_partner devient optionnel : on peut envoyer suggested_organisation à la place
            'suggested_partner': {'required': False},
        }

    def get_suggested_by_name(self, obj) -> str | None:
        u = obj.suggested_by
        if not u:
            return None
        return f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email

    def get_suggested_partner_name(self, obj) -> str | None:
        u = obj.suggested_partner
        if not u:
            return None
        return f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email

    def get_unique_together_validators(self):
        # Le modèle a unique_together (incident, suggested_partner). DRF en déduit
        # un UniqueTogetherValidator qui FORCE suggested_partner requis dans l'input
        # (enforce_required_fields), ce qui casse le chemin suggested_organisation
        # (où le partenaire n'est résolu qu'au moment du validate()). On désactive
        # ce validateur auto et on contrôle l'unicité manuellement dans validate().
        return []

    def validate(self, data):
        incident = data.get('incident') or getattr(self.instance, 'incident', None)
        if incident and incident.is_resolved:
            raise serializers.ValidationError(
                "Impossible de suggérer un partenaire sur un incident clôturé."
            )

        # Résolution organisation -> user : si le front envoie suggested_organisation,
        # on récupère son admin (ou bureau_agent) comme suggested_partner.
        org = data.pop('suggested_organisation', None)
        suggested_partner = data.get('suggested_partner') or getattr(
            self.instance, 'suggested_partner', None)

        if org and not suggested_partner:
            # On choisit en priorité un org_admin, sinon un bureau_agent
            partner_user = (
                User.objects.filter(organisation_member=org, org_role=ORG_ROLE_ADMIN).first()
                or User.objects.filter(organisation_member=org, org_role=ORG_ROLE_BUREAU).first()
            )
            if not partner_user:
                raise serializers.ValidationError({
                    "suggested_organisation": (
                        f"L'organisation '{org.name}' n'a aucun admin ou bureau_agent. "
                        "Impossible de la suggérer comme partenaire."
                    )
                })
            data['suggested_partner'] = partner_user
            suggested_partner = partner_user

        if not suggested_partner:
            raise serializers.ValidationError({
                "suggested_partner": (
                    "Vous devez fournir 'suggested_partner' (id user) ou "
                    "'suggested_organisation' (id organisation)."
                )
            })

        if incident and suggested_partner:
            # refuser si l'organisation est déjà collaboratrice acceptée
            already = Collaboration.objects.filter(
                incident=incident, user=suggested_partner, status='accepted'
            ).exists()
            if already:
                raise serializers.ValidationError(
                    "Cette organisation collabore déjà sur l'incident."
                )
            # unicité (incident, suggested_partner) gérée manuellement puisque le
            # validateur auto a été désactivé ci-dessus (get_unique_together_validators).
            dup_qs = PartnerSuggestion.objects.filter(
                incident=incident, suggested_partner=suggested_partner
            )
            if self.instance is not None:
                dup_qs = dup_qs.exclude(pk=self.instance.pk)
            if dup_qs.exists():
                raise serializers.ValidationError(
                    "Cette organisation a déjà été invitée ou suggérée pour cet incident."
                )
        return data


