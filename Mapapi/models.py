from django.db import models
from django.db import connection, transaction
from django.contrib.auth.models import (
    AbstractBaseUser, BaseUserManager, PermissionsMixin, Group, Permission)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import datetime, timedelta
import uuid
import random
# 
from .Send_mails import send_email
from django.conf import settings
from django.utils.html import format_html

# Import the custom storage classes
from backend.supabase_storage import ImageStorage, VideoStorage, VoiceStorage, DocumentStorage
from django.core.validators import FileExtensionValidator

ADMIN = 'admin'
VISITOR = 'visitor'
CITIZEN = 'citizen'
REPORTER = 'reporter'
BUSINESS = 'business'
ELU = 'elu'
FIELD_AGENT = 'field_agent'
DECLARED = 'declared'
RESOLVED = 'resolved'
IN_PROGRESS = "in_progress"
TAKEN = "taken_into_account"
# --- Phase 4 : nouveaux états du flux de résolution (additifs, non destructifs) ---
RESOLUTION_PREPARED = 'resolution_prepared'   # Résolution préparée (attente Admin)
IN_VALIDATION = 'in_validation'               # Résolu (en validation)
RESOLVED_DEFINITIVE = 'resolved_definitive'   # Résolu (définitif)

# --- Anti-gel (spec T3 / §5) : sévérité catégorielle de l'incident ---
# Pilote le délai d'échec de prise en compte : Élevée 30 j / Moyenne 60 j / Faible 90 j.
SEVERITY_HIGH = 'high'
SEVERITY_MEDIUM = 'medium'
SEVERITY_LOW = 'low'
SEVERITY_CHOICES = (
    (SEVERITY_HIGH, "Élevée"),
    (SEVERITY_MEDIUM, "Moyenne"),
    (SEVERITY_LOW, "Faible"),
)
# Mapping sévérité -> délai anti-gel en jours (None => fallback ANTI_GEL_DEFAULT_DAYS).
ANTI_GEL_DEADLINE_DAYS = {
    SEVERITY_HIGH: 30,
    SEVERITY_MEDIUM: 60,
    SEVERITY_LOW: 90,
}

USER_TYPES = (
    (ADMIN, ADMIN),
    (VISITOR, VISITOR),
    (REPORTER, REPORTER),
    (CITIZEN, CITIZEN),
    (BUSINESS, BUSINESS),
    (ELU, ELU),
    (FIELD_AGENT, FIELD_AGENT),
)
ETAT_INCIDENT = (
    (DECLARED, DECLARED),
    (RESOLVED, RESOLVED),
    (IN_PROGRESS, IN_PROGRESS),
    (TAKEN, TAKEN),
    # --- Phase 4 : nouveaux états du flux de résolution ---
    (RESOLUTION_PREPARED, "Résolution préparée (attente Admin)"),
    (IN_VALIDATION, "Résolu (en validation)"),
    (RESOLVED_DEFINITIVE, "Résolu (définitif)"),
)
ETAT_RAPPORT = (
    ("new", "new"),
    ("in_progress", "in_progress"),
    ("edit", "edit"),
    ("canceled", "canceled")
)

# --- Collaboration / Task constants ---
COLLAB_ROLE_LEADER = 'leader'
COLLAB_ROLE_CONTRIBUTOR = 'contributor'
COLLAB_ROLE_OBSERVER = 'observer'
COLLAB_ROLES = (
    (COLLAB_ROLE_LEADER, COLLAB_ROLE_LEADER),
    (COLLAB_ROLE_CONTRIBUTOR, COLLAB_ROLE_CONTRIBUTOR),
    (COLLAB_ROLE_OBSERVER, COLLAB_ROLE_OBSERVER),
)

TASK_PENDING = 'pending'
TASK_IN_PROGRESS = 'in_progress'
TASK_DONE = 'done'
TASK_FAILED = 'failed'
TASK_STATES = (
    (TASK_PENDING, TASK_PENDING),
    (TASK_IN_PROGRESS, TASK_IN_PROGRESS),
    (TASK_DONE, TASK_DONE),
    (TASK_FAILED, TASK_FAILED),
)

# --- Collaboration statuses (cf. spec §5 : En attente → Active → Terminée / Refusée) ---
# Valeurs historiques conservées (pending/accepted/declined). Ajout des états
# terminaux 'terminated' (Terminée) et 'refused' (Refusée). Choices uniquement :
# le champ status est un CharField sans `choices=` au niveau modèle, donc aucune
# migration n'est requise.
COLLAB_STATUS_PENDING = 'pending'
COLLAB_STATUS_ACCEPTED = 'accepted'
COLLAB_STATUS_DECLINED = 'declined'
COLLAB_STATUS_TERMINATED = 'terminated'
COLLAB_STATUS_REFUSED = 'refused'
COLLAB_STATUSES = (
    (COLLAB_STATUS_PENDING, 'En attente'),
    (COLLAB_STATUS_ACCEPTED, 'Active'),
    (COLLAB_STATUS_DECLINED, 'Refusée'),
    (COLLAB_STATUS_TERMINATED, 'Terminée'),
    (COLLAB_STATUS_REFUSED, 'Refusée'),
)

SUGGESTION_PENDING = 'pending'
SUGGESTION_ACCEPTED = 'accepted'
SUGGESTION_REJECTED = 'rejected'
SUGGESTION_STATUSES = (
    (SUGGESTION_PENDING, SUGGESTION_PENDING),
    (SUGGESTION_ACCEPTED, SUGGESTION_ACCEPTED),
    (SUGGESTION_REJECTED, SUGGESTION_REJECTED),
)
# Suggestions ne peuvent proposer que des rôles non-leader
SUGGESTION_ROLES = (
    (COLLAB_ROLE_CONTRIBUTOR, COLLAB_ROLE_CONTRIBUTOR),
    (COLLAB_ROLE_OBSERVER, COLLAB_ROLE_OBSERVER),
)

# Extensions autorisées pour les pièces jointes du chat
CHAT_ATTACHMENT_EXTENSIONS = ['pdf', 'doc', 'docx', 'xls', 'xlsx']

# --- Rôles internes à l'organisation ---
ORG_ROLE_ADMIN = 'org_admin'
ORG_ROLE_BUREAU = 'bureau_agent'
ORG_ROLE_FIELD = 'field_agent'
ORG_ROLES = (
    (ORG_ROLE_ADMIN, 'Admin organisation'),
    (ORG_ROLE_BUREAU, 'Agent de bureau'),
    (ORG_ROLE_FIELD, 'Agent de terrain'),
)

# --- Secteurs d'activité d'une organisation (valeur stockée → libellé FR) ---
ORG_SECTOR_ENVIRONMENT = 'environment'
ORG_SECTOR_SANITATION = 'sanitation'
ORG_SECTOR_WATER_WASH = 'water_wash'
ORG_SECTOR_HEALTH = 'health'
ORG_SECTOR_FOOD_SECURITY = 'food_security'
ORG_SECTOR_PROTECTION = 'protection'
ORG_SECTOR_HUMANITARIAN = 'humanitarian'
ORG_SECTOR_DEVELOPMENT = 'development'
ORG_SECTOR_GOVERNANCE = 'governance'
ORG_SECTOR_EDUCATION = 'education'
ORG_SECTOR_TECHNOLOGY_DATA = 'technology_data'
ORG_SECTOR_MULTISECTOR = 'multisector'
ORG_SECTOR_OTHER = 'other'
ORG_ACTIVITY_SECTORS = (
    (ORG_SECTOR_ENVIRONMENT, 'Environnement'),
    (ORG_SECTOR_SANITATION, 'Assainissement'),
    (ORG_SECTOR_WATER_WASH, 'Eau / WASH'),
    (ORG_SECTOR_HEALTH, 'Santé'),
    (ORG_SECTOR_FOOD_SECURITY, 'Sécurité alimentaire'),
    (ORG_SECTOR_PROTECTION, 'Protection'),
    (ORG_SECTOR_HUMANITARIAN, 'Humanitaire'),
    (ORG_SECTOR_DEVELOPMENT, 'Développement'),
    (ORG_SECTOR_GOVERNANCE, 'Gouvernance'),
    (ORG_SECTOR_EDUCATION, 'Éducation'),
    (ORG_SECTOR_TECHNOLOGY_DATA, 'Technologie / Données'),
    (ORG_SECTOR_MULTISECTOR, 'Multisectoriel'),
    (ORG_SECTOR_OTHER, 'Autre'),
)

# --- Types d'organisation (valeur stockée → libellé FR) ---
ORG_TYPE_NGO = 'ngo'
ORG_TYPE_INTERNATIONAL = 'international_organisation'
ORG_TYPE_UN_AGENCY = 'un_agency'
ORG_TYPE_PUBLIC_INSTITUTION = 'public_institution'
ORG_TYPE_LOCAL_AUTHORITY = 'local_authority'
ORG_TYPE_ASSOCIATION_CSO = 'association_cso'
ORG_TYPE_PRIVATE_SECTOR = 'private_sector'
ORG_TYPE_PROJECT_PROGRAM = 'project_program'
ORG_TYPE_COMMUNITY_STRUCTURE = 'community_structure'
ORG_TYPE_OTHER = 'other'
ORG_TYPES = (
    (ORG_TYPE_NGO, 'ONG'),
    (ORG_TYPE_INTERNATIONAL, 'Organisation internationale'),
    (ORG_TYPE_UN_AGENCY, 'Agence UN'),
    (ORG_TYPE_PUBLIC_INSTITUTION, 'Institution publique'),
    (ORG_TYPE_LOCAL_AUTHORITY, 'Collectivité territoriale'),
    (ORG_TYPE_ASSOCIATION_CSO, 'Association / OSC'),
    (ORG_TYPE_PRIVATE_SECTOR, 'Secteur privé'),
    (ORG_TYPE_PROJECT_PROGRAM, 'Projet / Programme'),
    (ORG_TYPE_COMMUNITY_STRUCTURE, 'Structure communautaire'),
    (ORG_TYPE_OTHER, 'Autre'),
)

COUNTRY_SENEGAL = 'senegal'
COUNTRY_MALI = 'mali'
COUNTRY_GUINEA = 'guinea'
COUNTRY_BURKINA_FASO = 'burkina_faso'
COUNTRY_NIGER = 'niger'
COUNTRY_COTE_DIVOIRE = 'cote_divoire'
COUNTRY_MAURITANIA = 'mauritania'
INTERVENTION_COUNTRIES = (
    (COUNTRY_SENEGAL, 'Sénégal'),
    (COUNTRY_MALI, 'Mali'),
    (COUNTRY_GUINEA, 'Guinée'),
    (COUNTRY_BURKINA_FASO, 'Burkina Faso'),
    (COUNTRY_NIGER, 'Niger'),
    (COUNTRY_COTE_DIVOIRE, "Côte d’Ivoire"),
    (COUNTRY_MAURITANIA, 'Mauritanie'),
)

PARTNER_STATUS_ACTIVE = 'active'
PARTNER_STATUS_INACTIVE = 'inactive'
PARTNER_STATUSES = (
    (PARTNER_STATUS_ACTIVE, 'Actif'),
    (PARTNER_STATUS_INACTIVE, 'Inactif'),
)

ASSIGNMENT_PENDING = 'pending'
ASSIGNMENT_IN_PROGRESS = 'in_progress'
ASSIGNMENT_REPORTED = 'reported'
ASSIGNMENT_CANCELLED = 'cancelled'
ASSIGNMENT_STATUSES = (
    (ASSIGNMENT_PENDING, 'En attente'),
    (ASSIGNMENT_IN_PROGRESS, 'En cours'),
    (ASSIGNMENT_REPORTED, 'Rapport effectué'),
    (ASSIGNMENT_CANCELLED, 'Annulé'),
)

# Phase 4 — assignation d'un incident à une ORGANISATION par le Super Admin
# (spec §2/§3, T5 : jamais directement à un agent). L'Admin de l'organisation
# cible accepte/décline sous 72 h, sinon acceptation tacite (D4).
ORG_ASSIGNMENT_PENDING = 'pending'
ORG_ASSIGNMENT_ACCEPTED = 'accepted'
ORG_ASSIGNMENT_DECLINED = 'declined'
ORG_ASSIGNMENT_STATUSES = (
    (ORG_ASSIGNMENT_PENDING, 'En attente'),
    (ORG_ASSIGNMENT_ACCEPTED, 'Acceptée'),
    (ORG_ASSIGNMENT_DECLINED, 'Déclinée'),
)


class UUIDModel(models.Model):
    """Base abstraite : clé primaire UUID (au lieu d'un entier auto-incrémenté)
    pour éviter l'énumération/devinette des identifiants (faille IDOR)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


# Modèle d'organisation pour gérer les organisations liées aux utilisateurs
class Organisation(UUIDModel):
    name = models.CharField(max_length=255, unique=True)
    acronym = models.CharField(max_length=50, blank=True, null=True)
    is_premium = models.BooleanField(default=False)
    subdomain = models.CharField(max_length=255, unique=True)  # ex: wetlands
    logo = models.ImageField(
        upload_to='organisations/logos/',
        storage=ImageStorage(),
        null=True, blank=True,
        help_text="Logo de l'organisation (upload).",
    )
    activity_sector = models.CharField(max_length=40, choices=ORG_ACTIVITY_SECTORS, blank=True, null=True)
    organisation_type = models.CharField(max_length=40, choices=ORG_TYPES, blank=True, null=True)
    intervention_country = models.CharField(max_length=30, choices=INTERVENTION_COUNTRIES, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    partner_status = models.CharField(max_length=20, choices=PARTNER_STATUSES, default=PARTNER_STATUS_ACTIVE)
    phone = models.CharField(max_length=20, blank=True, null=True)
    website_url = models.URLField(null=True, blank=True)
    primary_color = models.CharField(max_length=7, default="#4CAF50")  # hex
    secondary_color = models.CharField(max_length=7, default="#8BC34A")
    background_color = models.CharField(max_length=7, default="#F0F0F0")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def get_members(self):
        """Tous les membres de l'organisation."""
        return self.members.all()

    def get_agents(self):
        """Agents de terrain de l'organisation."""
        return self.members.filter(org_role=ORG_ROLE_FIELD)

    def get_bureau_agents(self):
        """Agents de bureau de l'organisation."""
        return self.members.filter(org_role=ORG_ROLE_BUREAU)

    def get_admins(self):
        """Admins de l'organisation."""
        return self.members.filter(org_role=ORG_ROLE_ADMIN)

# Creation du model User pour les utilisateurs de l'application pour securiser l'entree des commandes

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email=None, phone=None, password=None, **extra_fields):
        """
        Creates and saves a User with the given email and password.
        """
        if not email and not phone:
            raise ValueError('The given email or phone number must be set')
        
        # Générer un email fictif si non fourni
        if not email:
            email = f"{phone}@example.com"
        
        email = self.normalize_email(email)
        user = self.model(email=email, phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


    def get_or_create_user(self, email=None, phone=None, password=None, **extra_fields):
        """
        Get an existing user by phone or create a new one with a dummy email if needed.
        """
        if not email and not phone:
            raise ValueError('un email ou un numéro de téléphone est requiert')
        
        user = self.filter(phone=phone).first()
        if user is None:
            user = self._create_user(email=email, phone=phone, password=password, **extra_fields)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """
        Creates and saves a regular user with the given email and password.
        """
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('is_staff', False)
        
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Creates and saves a superuser with the given email and password.
        """
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_staff', True)

        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    # Clé primaire UUID (cf. UUIDModel ; User n'en hérite pas car AbstractBaseUser).
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    groups = models.ManyToManyField(
        Group,
        related_name="mapapi_user_groups",
        blank=True,
        verbose_name="groups",
        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
    ),
    user_permissions = models.ManyToManyField(
        Permission,
        related_name="mapapi_user_user_permissions",
        blank=True,
        verbose_name="user permissions",
        help_text="Specific permissions for this user.",
    )

    email = models.EmailField(unique=True)
    first_name = models.CharField(_('first name'), max_length=255, blank=False)
    last_name = models.CharField(_('last name'), max_length=255, blank=False)
    phone = models.CharField(_('phone number'), max_length=20, blank=True, null=True)
    date_joined = models.DateTimeField(_('date joined'), auto_now_add=True)
    is_active = models.BooleanField(_('active'), default=True)
    is_staff = models.BooleanField(default=False)
    avatar = models.ImageField(default="avatars/default.png", upload_to='avatars/', 
                        storage=ImageStorage(),
                        null=True, blank=True)
    password_reset_count = models.DecimalField(max_digits=10, decimal_places=0, null=True, blank=True, default=0)
    address = models.CharField(_('adress'), max_length=255, blank=True, null=True)
    user_type = models.CharField(
        max_length=15, choices=USER_TYPES, blank=False, null=False, default=CITIZEN)
    community = models.ForeignKey('Communaute', db_column='user_communaute_id', related_name='user_communaute',
                                   on_delete=models.CASCADE, null=True, blank=True)
    provider = models.CharField(_('provider'), max_length=255, blank=True, null=True)
    organisation = models.CharField(_('organisation'), max_length=255, blank=True, null=True)
    # --- Lot 1 : lien réel vers Organisation + rôle interne ---
    organisation_member = models.ForeignKey(
        'Organisation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='members',
        help_text="Organisation à laquelle appartient l'utilisateur."
    )
    org_role = models.CharField(
        max_length=20, choices=ORG_ROLES,
        null=True, blank=True,
        help_text="Rôle interne dans l'organisation (org_admin, bureau_agent, field_agent)."
    )
    agent_code = models.CharField(
        max_length=10, unique=True, null=True, blank=True,
        help_text="Code auto-généré pour la connexion des agents de terrain."
    )
    pin_code = models.CharField(
        max_length=128, null=True, blank=True,
        help_text="PIN hashé pour la connexion des agents de terrain (4 chiffres)."
    )
    must_change_pin = models.BooleanField(
        default=False,
        help_text="Si True, l'agent doit changer son PIN à la prochaine connexion."
    )
    points = models.IntegerField(null=True, blank=True, default=0)
    zones = models.ManyToManyField('Zone', blank=True)
    verification_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_expiration = models.DateTimeField(blank=True, null=True)
    # Dernière consultation du flux d'activité (vues/non-vues) : tout élément du
    # flux postérieur à cette date est considéré « non vu » par l'utilisateur.
    activity_seen_at = models.DateTimeField(blank=True, null=True)
    objects = UserManager()

    USERNAME_FIELD = 'email'
    # these field are required on registering
    REQUIRED_FIELDS = ['first_name', 'last_name']
    is_deleted = models.BooleanField(default=False,
                                     help_text="Si True, l'utilisateur a été supprimé (corbeille).")

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def __str__(self):
        return self.email

    def get_full_name(self):
        '''
        Returns the first_name plus the last_name, with a space in between.
        '''
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        '''
        Returns the short name for the user.
        '''
        return self.first_name
        
    def generate_otp(self):
        self.otp = str(random.randint(100000, 999999))
        self.otp_expiration = timezone.now() + timedelta(minutes=5)
        self.save()

    def send_verification_email(self):
        verification_link = f"https://api.map-action.com/MapApi/web_verify-email/{self.verification_token}"
        context = {"verification_link": verification_link}
        subject = "Vérification de votre compte"
        template_name = "emails/verification_email.html"
        to_email = self.email

        send_email.delay(subject, template_name, context, to_email)

    # def generate_otp(self):
    #     self.otp = str(random.randint(100000, 999999))
    #     self.otp_expiration = timezone.now() + timedelta(minutes=5)
    #     self.save()

    def is_otp_valid(self):
        if not self.otp or not self.otp_expiration:
            return False
        
        otp_expiry_time = timedelta(minutes=5)  
        if timezone.now() - self.otp_expiration > otp_expiry_time:
            return False
        
        return True

    def generate_agent_code(self):
        """Génère un code unique pour un agent de terrain."""
        import string
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not User.objects.filter(agent_code=code).exists():
                self.agent_code = code
                self.save(update_fields=['agent_code'])
                return code

    def generate_and_set_pin(self, force_change=True):
        """Génère un PIN aléatoire 4 chiffres, le hash, et le stocke.

        Args:
            force_change: si True, met must_change_pin=True (première connexion).

        Returns:
            Le PIN en clair (à communiquer à l'agent une seule fois).
        """
        from django.contrib.auth.hashers import make_password
        pin = f"{random.randint(1000, 9999)}"
        self.pin_code = make_password(pin)
        self.must_change_pin = force_change
        self.save(update_fields=['pin_code', 'must_change_pin'])
        return pin

    def check_pin(self, pin):
        """Vérifie si un PIN en clair correspond au PIN hashé."""
        from django.contrib.auth.hashers import check_password
        return check_password(pin, self.pin_code)


class FieldReport(UUIDModel):
    """Rapport de déplacement d'un agent de terrain sur le lieu d'un incident."""
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='field_reports')
    incident = models.ForeignKey('Incident', on_delete=models.CASCADE, related_name='field_reports')
    location_lat = models.CharField(max_length=250, blank=True, null=True,
                                    help_text="Latitude réelle de l'agent lors du déplacement.")
    location_lon = models.CharField(max_length=250, blank=True, null=True,
                                    help_text="Longitude réelle de l'agent lors du déplacement.")
    distance_meters = models.FloatField(null=True, blank=True,
                                        help_text="Distance estimée entre l'agent et le lieu de l'incident (m).")
    notes = models.TextField(max_length=1000, blank=True, null=True,
                             help_text="Observations de l'agent sur l'état des lieux.")
    photo = models.ImageField(upload_to='field_reports/',
                              storage=ImageStorage(),
                              null=True, blank=True)
    visited_at = models.DateTimeField(default=timezone.now,
                                      help_text="Date et heure du déplacement.")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Rapport terrain - {self.agent} sur {self.incident} ({self.visited_at:%d/%m/%Y})"

    class Meta:
        ordering = ('-visited_at',)


class IncidentAssignment(UUIDModel):
    incident = models.ForeignKey('Incident', on_delete=models.CASCADE, related_name='assignments')
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='incident_assignments')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_incident_assignments')
    deadline = models.DateTimeField()
    status = models.CharField(max_length=20, choices=ASSIGNMENT_STATUSES, default=ASSIGNMENT_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("incident", "agent"),)
        ordering = ('deadline', '-created_at')

    def __str__(self):
        return f"{self.incident} assigné à {self.agent} avant {self.deadline:%d/%m/%Y %H:%M}"


class IncidentOrgAssignment(UUIDModel):
    """Assignation d'un incident à une ORGANISATION par le Super Admin (spec §2/§3, T5).

    Distinct du modèle AGENT-centrique `IncidentAssignment` : ici la cible est
    une organisation, jamais un agent. L'Admin de l'organisation cible accepte
    ou décline sous 72 h ; sans réponse, acceptation tacite (D4). À l'acceptation,
    l'organisation engage l'incident (« Pris en compte »).
    """
    incident = models.ForeignKey(
        'Incident', on_delete=models.CASCADE, related_name='org_assignments'
    )
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_org_assignments'
    )
    status = models.CharField(
        max_length=20, choices=ORG_ASSIGNMENT_STATUSES, default=ORG_ASSIGNMENT_PENDING
    )
    decline_reason = models.TextField(null=True, blank=True)
    deadline = models.DateTimeField(help_text="Échéance d'acceptation (now + 72 h).")
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"Incident {self.incident_id} → orga {self.organisation_id} ({self.status})"


class Incident(UUIDModel):
    title = models.CharField(max_length=250, blank=True,
                             null=True)
    zone = models.CharField(max_length=250, blank=False,
                            null=False)
    description = models.TextField(max_length=500, blank=True, null=True)
    photo = models.ImageField(upload_to='incidents/',
                        storage=ImageStorage(),
                        null=True, blank=True)
    # Miniature générée automatiquement à partir de `photo` (cf. save()) pour
    # alléger le chargement de l'onglet incidents. Lecture seule côté API.
    thumbnail = models.ImageField(upload_to='incidents/thumbnails/',
                        storage=ImageStorage(),
                        null=True, blank=True)
    video = models.FileField(upload_to='incidents/',
                        storage=VideoStorage(),
                        blank=True, null=True)
    audio = models.FileField(upload_to='incidents/', 
                        storage=VoiceStorage(), 
                        blank=True, null=True)
    user_id = models.ForeignKey('User', db_column='user_incid_id', related_name='user_incident',
                                on_delete=models.CASCADE, null=True)
    lattitude = models.CharField(max_length=250, blank=True,
                                 null=True)
    longitude = models.CharField(max_length=250, blank=True,
                                 null=True)
    etat = models.CharField(
        max_length=255, choices=ETAT_INCIDENT, blank=False, null=False, default=DECLARED)
    category_id = models.ForeignKey('Category', db_column='categ_incid_id', related_name='user_category',
                                    on_delete=models.CASCADE, null=True)
    indicateur_id = models.ForeignKey('Indicateur', db_column='indic_incid_id', related_name='user_indicateur',
                                      on_delete=models.CASCADE, null=True)
    slug = models.CharField(max_length=250, blank=True,
                            null=True)
    category_ids = models.ManyToManyField('Category', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    taken_by = models.ForeignKey(User, related_name='taken_incidents', null=True, blank=True, on_delete=models.SET_NULL)
    # Mode de prise en charge : 'internal' (org seule en interne) ou 'collaborative' (ouvert aux autres orgs)
    TAKE_IN_CHARGE_MODES = (
        ('internal', 'Interne (organisation seule)'),
        ('collaborative', 'Collaborative (ouvert aux autres organisations)'),
    )
    take_in_charge_mode = models.CharField(
        max_length=20, choices=TAKE_IN_CHARGE_MODES, null=True, blank=True,
        help_text="Mode de prise en charge choisi par la première organisation."
    )
    # --- Spec : suivi résolution incident ---
    resolution_start_date = models.DateField(null=True, blank=True,
                                             help_text="Date de début de la résolution. Obligatoire à la clôture.")
    resolution_end_date = models.DateField(null=True, blank=True,
                                           help_text="Date de fin de la résolution. Obligatoire à la clôture.")
    progress = models.PositiveSmallIntegerField(default=0,
                                                help_text="Progression auto-calculée (0-100) selon avancement des tâches.")
    is_public = models.BooleanField(default=True,
                                     help_text="Si False, l'incident n'est visible que par l'organisation de l'agent.")
    is_deleted = models.BooleanField(default=False,
                                     help_text="Si True, l'incident a été supprimé (corbeille).")
    deleted_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Horodatage de la mise en corbeille (is_deleted=True). Sert à la purge des 30 j (spec D10)."
    )
    taken_in_charge_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Horodatage de la prise en compte (passage en 'taken_into_account'). "
                  "Sert au calcul du délai anti-gel (spec T3)."
    )
    # --- Anti-gel (spec T3 / §5) : sévérité + drapeaux d'avertissement (75 % / 90 %) ---
    severity = models.CharField(
        max_length=10, choices=SEVERITY_CHOICES, null=True, blank=True,
        default=SEVERITY_MEDIUM,
        help_text="Sévérité catégorielle. Pilote le délai anti-gel "
                  "(Élevée 30 j / Moyenne 60 j / Faible 90 j ; défaut/inconnue : 60 j)."
    )
    antigel_warned_75 = models.BooleanField(
        default=False,
        help_text="Avertissement anti-gel à 75 % du délai déjà envoyé au leader. "
                  "Remis à False à chaque (re)prise en compte (spec T3)."
    )
    antigel_warned_90 = models.BooleanField(
        default=False,
        help_text="Avertissement anti-gel à 90 % du délai déjà envoyé au leader. "
                  "Remis à False à chaque (re)prise en compte (spec T3)."
    )
    # --- Phase 4 : flux de résolution (résolution préparée → validation → définitif) ---
    resolution_submitted_by = models.ForeignKey(
        User, related_name='+', null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Membre (agent de bureau/admin) ayant monté le dossier de résolution."
    )
    resolution_submitted_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Date de soumission du dossier de résolution préparée."
    )
    validation_deadline = models.DateTimeField(
        null=True, blank=True,
        help_text="Échéance de contrôle Super Admin (72h après déclaration de résolution)."
    )
    rejection_reason = models.TextField(
        null=True, blank=True,
        help_text="Motif de refus de la résolution par le Super Admin."
    )

    def __str__(self):
        return self.zone + ' '

    def save(self, *args, **kwargs):
        # Génère une miniature (≈320px) à partir de la photo, une seule fois, pour
        # alléger le chargement de l'onglet incidents. N'échoue jamais la sauvegarde
        # de l'incident si la génération de la miniature échoue.
        if self.photo and not self.thumbnail:
            self._generate_thumbnail()
        # Un incident résolu/clôturé est à 100% de progression — même s'il n'a aucune
        # tâche (sinon `progress` restait à 0 et le front affichait 0% pour un incident
        # résolu). On ajoute 'progress' à update_fields si fourni, pour bien le persister.
        if self.etat in (RESOLVED, RESOLVED_DEFINITIVE) and self.progress != 100:
            self.progress = 100
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = list(set(update_fields) | {'progress'})
        super().save(*args, **kwargs)

    def _generate_thumbnail(self, size=(320, 320)):
        import logging
        from io import BytesIO
        from PIL import Image
        from django.core.files.base import ContentFile
        try:
            self.photo.seek(0)
            data = self.photo.read()
            self.photo.seek(0)  # réinitialise le flux : la photo doit se sauvegarder intacte
            img = Image.open(BytesIO(data)).convert('RGB')
            img.thumbnail(size)  # conserve le ratio, borne à size
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=80, optimize=True)
            self.thumbnail.save(f"thumb_{self.pk}.jpg", ContentFile(buf.getvalue()), save=False)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "Génération miniature échouée pour l'incident %s: %s", self.pk, exc)

    def update_progress(self, save=True):
        """Recalcule la progression de l'incident en fonction de ses tâches confirmées.

        Seules les tâches confirmées par le leader (is_confirmed=True) sont prises en compte.
        Une tâche 'done' compte comme terminée (poids 1).
        Une tâche 'failed' est considérée comme close (poids 1) mais ne contribue pas à 100%.
        Progression = round(done / total * 100).
        """
        # Un incident résolu est à 100% quoi qu'il arrive (clôture = terminé).
        if self.etat in (RESOLVED, RESOLVED_DEFINITIVE):
            self.progress = 100
        else:
            tasks = self.tasks.filter(is_confirmed=True)
            total = tasks.count()
            if total == 0:
                self.progress = 0
            else:
                done = tasks.filter(state=TASK_DONE).count()
                self.progress = round(done * 100 / total)
        if save:
            self.save(update_fields=['progress'])
        return self.progress

    @property
    def is_resolved(self):
        return self.etat == RESOLVED

    def can_add_task(self):
        """Une tâche ne peut être ajoutée qu'avant la clôture."""
        return not self.is_resolved

    def can_suggest_partner(self):
        """Une suggestion ne peut être faite qu'avant la clôture."""
        return not self.is_resolved

    @property
    def reported_by_agent(self):
        """True si l'incident a été reporté par un agent de terrain."""
        if self.user_id and hasattr(self.user_id, 'org_role'):
            return self.user_id.org_role == 'field_agent'
        return False


class Evenement(UUIDModel):
    title = models.CharField(max_length=255, blank=True,
                             null=True)
    zone = models.CharField(max_length=255, blank=False,
                            null=False)
    description = models.TextField(max_length=500, blank=True, null=True)
    photo = models.ImageField(upload_to='events/',
                        storage=ImageStorage(),
                        null=True, blank=True)
    date = models.DateTimeField(null=True)
    lieu = models.CharField(max_length=250, blank=False,
                            null=False)
    video = models.FileField(upload_to='events/',
                        storage=VideoStorage(),
                        blank=True, null=True)
    audio = models.FileField(upload_to='events/',
                        storage=VoiceStorage(),
                        blank=True, null=True)
    user_id = models.ForeignKey('User', db_column='user_event_id', related_name='user_event', on_delete=models.CASCADE,
                                null=True)
    latitude = models.CharField(max_length=1000, blank=True, null=True)
    longitude = models.CharField(max_length=1000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.zone + ' '


class Contact(UUIDModel):
    objet = models.CharField(max_length=250, blank=False,
                             null=False)
    message = models.TextField(max_length=500, blank=True, null=True)
    email = models.CharField(max_length=250, blank=True,
                             null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.objet + ' '


class Communaute(UUIDModel):
    name = models.CharField(max_length=250, blank=False,
                            null=False)
    zone = models.ForeignKey('Zone', db_column='zone_communaute_id', related_name='Zone_communaute',
                             on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name + ' '


class Rapport(UUIDModel):
    details = models.CharField(max_length=500, blank=False,
                               null=False)
    type = models.CharField(max_length=500, blank=True,
                            null=True)
    incident = models.ForeignKey('Incident', db_column='incident_rapport_id', related_name='incident_rapport',
                                 on_delete=models.CASCADE, null=True)
    zone = models.CharField(max_length=250, blank=False, null=True)
    user_id = models.ForeignKey('User', db_column='user_rapport_id', related_name='user_rapport',
                                on_delete=models.CASCADE, null=True)
    date_livraison = models.CharField(max_length=100, blank=True,
                                      null=True)
    statut = models.CharField(
        max_length=15, choices=ETAT_RAPPORT, blank=False, null=False, default="new")
    incidents = models.ManyToManyField('Incident', blank=True)
    disponible = models.BooleanField(_('active'), default=False)
    file = models.FileField(upload_to='reports/',
                        storage=ImageStorage(),
                        blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.details + ' '


class Participate(UUIDModel):
    evenement_id = models.ForeignKey('Evenement', db_column='event_participate_id', related_name='event_participate',
                                     on_delete=models.CASCADE, null=True)
    user_id = models.ForeignKey('User', db_column='user_participate_id', related_name='user_participate',
                                on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Zone(UUIDModel):
    name = models.CharField(max_length=250, blank=False,
                            null=False, unique=True)
    description = models.TextField(max_length=500, blank=True, null=True)  # Added description field
    lattitude = models.CharField(max_length=250, blank=True,
                                 null=True)
    longitude = models.CharField(max_length=250, blank=True,
                                 null=True)
    photo = models.ImageField(upload_to='zones/',
                        storage=ImageStorage(),
                        null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name + ' '


class Message(UUIDModel):
    objet = models.CharField(max_length=250, blank=False,
                             null=False)
    message = models.CharField(max_length=250, blank=False, null=False)

    zone = models.ForeignKey('Zone', db_column='mess_zone_id', related_name='zone_mess', on_delete=models.CASCADE,
                             null=True)
    communaute = models.ForeignKey('Communaute', db_column='mess_communaute_id', related_name='communaute_mess',
                                   on_delete=models.CASCADE, null=True)
    user_id = models.ForeignKey('User', db_column='user_mess_id', related_name='user_mess', on_delete=models.CASCADE,
                                null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.objet + ' '


class ResponseMessage(UUIDModel):
    response = models.CharField(max_length=250, blank=False, null=False)

    message = models.ForeignKey('Message', db_column='mess_resp_id', related_name='resp_mess', on_delete=models.CASCADE,
                                null=True)
    elu = models.ForeignKey('User', db_column='user_mess_id', related_name='user_resp', on_delete=models.CASCADE,
                            null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.response + ' '


class Category(UUIDModel):
    name = models.CharField(max_length=250, blank=False,
                            null=False, unique=True)
    description = models.TextField(max_length=500, blank=True, null=True)  # Added description field
    photo = models.ImageField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name + ' '


class Indicateur(UUIDModel):
    name = models.CharField(max_length=250, blank=False,
                            null=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name + ' '


class PasswordReset(UUIDModel):
    code = models.CharField(max_length=7, blank=False, null=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, blank=False, null=False, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)
    date_used = models.DateTimeField(null=True)


class ImageBackground(UUIDModel):
    photo = models.ImageField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

# verification code otp
class PhoneOTP(UUIDModel):
    phone_number = models.CharField(max_length=15)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

# Collaboration table
class Collaboration(UUIDModel):
    incident = models.ForeignKey('Incident', blank=False, null=False, on_delete=models.CASCADE)
    user = models.ForeignKey(User, blank=False, null=False, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    end_date = models.DateField(blank=True, null=True)
    motivation = models.TextField(blank=True, null=True)
    other_option = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, default='pending')
    role = models.CharField(max_length=20, choices=COLLAB_ROLES, default=COLLAB_ROLE_CONTRIBUTOR,
                            help_text="Rôle de l'organisation sur l'incident : leader, contributor ou observer.")

    class Meta:
        unique_together = (("incident", "user"),)

    def __str__(self):
        return f"Collaboration on {self.incident} by {self.user} ({self.role})"
    
# Collaboration table
class Colaboration(UUIDModel):
    incident = models.ForeignKey('Incident', blank=False, null=False, on_delete=models.CASCADE)
    user = models.ForeignKey(User, blank=False, null=False, on_delete=models.CASCADE)
    end_date = models.DateField()
    motivation = models.TextField(blank=True, null=True)  
    other_option = models.CharField(max_length=255, blank=True, null=True) 
    status = models.CharField(max_length=20, default='pending')  

    def __str__(self):
        return f"Collaboration on {self.incident} by {self.user}"


class PredictionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    COMPLETED_WITH_WARNING = "completed_with_warning", "Completed with warning"
    FAILED = "failed", "Failed"


class Prediction(UUIDModel):
    # --- Legacy fields (kept nullable for backward compatibility) ---
    # NOTE: ``incident_id`` was the legacy CharField. It has been renamed to
    # ``legacy_incident_id`` because the new ``incident`` ForeignKey below
    # auto-creates an attribute named ``incident_id`` (the FK column).
    prediction_id = models.IntegerField(unique=True, blank=True, null=True, default=None)
    legacy_incident_id = models.CharField(max_length=255, blank=True, null=True)
    incident_type = models.CharField(max_length=255, blank=True, null=True)
    piste_solution = models.TextField(blank=True, null=True)
    analysis = models.TextField(blank=True, null=True)
    ndvi_heatmap = models.TextField(blank=True, null=True)
    ndvi_ndwi_plot = models.TextField(blank=True, null=True)
    landcover_plot = models.TextField(blank=True, null=True)

    # --- New model-deploy integration fields ---
    incident = models.OneToOneField(
        'Incident', on_delete=models.CASCADE,
        related_name='prediction', null=True, blank=True
    )
    status = models.CharField(
        max_length=32, choices=PredictionStatus.choices,
        default=PredictionStatus.PENDING
    )

    macro_category = models.CharField(max_length=255, blank=True, default='')
    sub_category = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True, default='')

    source_size_meters = models.FloatField(null=True, blank=True)
    spread_vectors = models.JSONField(default=list, blank=True)

    impact_radius_meters = models.FloatField(null=True, blank=True)
    radius_explanation = models.TextField(blank=True, default='')

    global_impact_score = models.FloatField(null=True, blank=True)
    base_severity = models.IntegerField(null=True, blank=True)
    impact_tags = models.JSONField(default=list, blank=True)

    recommendation = models.TextField(blank=True, default='')

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    city = models.CharField(max_length=255, blank=True, default='')
    region = models.CharField(max_length=255, blank=True, default='')
    country = models.CharField(max_length=255, blank=True, default='')
    display_name = models.TextField(blank=True, default='')

    social_vulnerability_score = models.FloatField(null=True, blank=True)
    is_social_probabilistic = models.BooleanField(default=False)

    total_population_exposed = models.IntegerField(default=0)
    adult_men_exposed = models.IntegerField(default=0)
    adult_women_exposed = models.IntegerField(default=0)
    children_exposed = models.IntegerField(default=0)
    maternities_count = models.IntegerField(default=0)
    nurseries_count = models.IntegerField(default=0)

    health_centers = models.IntegerField(default=0)
    maternities = models.IntegerField(default=0)
    schools = models.IntegerField(default=0)
    nurseries = models.IntegerField(default=0)
    markets = models.IntegerField(default=0)
    water_points = models.IntegerField(default=0)
    main_roads_bridges = models.IntegerField(default=0)
    residential_buildings = models.IntegerField(default=0)

    ai_analysis = models.JSONField(default=dict, blank=True)
    topography = models.JSONField(default=dict, blank=True)
    satellite = models.JSONField(default=dict, blank=True)
    social_data = models.JSONField(default=dict, blank=True)
    human_impact = models.JSONField(default=dict, blank=True)
    geocoding = models.JSONField(default=dict, blank=True)
    potential_risk = models.JSONField(null=True, blank=True)
    full_response = models.JSONField(default=dict, blank=True)

    error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.prediction_id:
            # Use a savepoint so that a missing legacy sequence does not
            # abort the surrounding transaction (which would otherwise
            # poison every subsequent query in the same request).
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT nextval('Mapapi_prediction_new_id_seq')"
                        )
                        self.prediction_id = cursor.fetchone()[0]
            except Exception:
                # The legacy sequence may not exist on fresh databases.
                self.prediction_id = None
        # Keep legacy ``legacy_incident_id`` (CharField) aligned with the FK
        # so any old code reading the previous column keeps working.
        if self.incident and not self.legacy_incident_id:
            self.legacy_incident_id = str(self.incident.pk)
        super().save(*args, **kwargs)


NOTIF_TYPE_TITLES = {
    'collaboration_request': 'Demande de collaboration',
    'collaboration_accepted': 'Collaboration acceptée',
    'collaboration_declined': 'Collaboration refusée',
    'deadline_warning': 'Alerte délai',
    'incident_report': 'Nouvel incident signalé',
    'incident_assignment': 'Incident assigné',
}


class Notification(UUIDModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)
    # Catégorie de la notification (pour titre/icône côté front, plus de titre en
    # dur). cf. NOTIF_TYPE_TITLES pour le libellé FR par défaut.
    notif_type = models.CharField(max_length=40, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)
    # Rendu nullable (Phase 4 — Feature 3 « Signaler à mon Admin ») : une
    # notification peut désormais exister sans collaboration rattachée.
    colaboration = models.ForeignKey(Collaboration, on_delete=models.CASCADE, null=True, blank=True)
    # Incident concerné (pour la redirection au clic sur la notification).
    incident = models.ForeignKey('Incident', on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)

    def __str__(self):
        return self.message

    @property
    def title(self):
        """Titre FR par défaut selon le type (le front peut le surcharger)."""
        return NOTIF_TYPE_TITLES.get(self.notif_type, 'Notification')

    def redirect_link(self):
        """Cible de redirection au clic sur la notification (ou None).

        - ``collaboration_request`` (demande REÇUE par le leader) → page collaboration,
          onglet « Demandes » (là où on accepte/refuse), PAS le détail.
        - autre notif de collaboration (acceptée/refusée…) → détail de la collaboration,
          via le **collaboration_id** (et non l'incident_id — c'est l'id attendu par la
          route ``/collaboration-detail/<id>``).
        - sinon, si un incident est lié → page de l'incident.
        """
        incident_id = self.incident_id or getattr(getattr(self, 'colaboration', None), 'incident_id', None)
        if self.colaboration_id:
            collab_id = str(self.colaboration_id)
            inc = str(incident_id) if incident_id else None
            if self.notif_type == 'collaboration_request':
                return {'type': 'collaboration_request', 'tab': 'requests',
                        'collaboration_id': collab_id, 'incident_id': inc,
                        'url': '/collaboration?tab=requests'}
            return {'type': 'collaboration', 'tab': 'mes-collaborations',
                    'collaboration_id': collab_id, 'incident_id': inc,
                    'url': f'/collaboration-detail/{collab_id}'}
        if incident_id:
            return {'type': 'incident', 'incident_id': str(incident_id),
                    'url': f'/incidents/{incident_id}'}
        return None


CHAT_ROLE_USER = 'user'
CHAT_ROLE_ASSISTANT = 'assistant'
CHAT_ROLE_SYSTEM = 'system'
CHAT_ROLES = (
    (CHAT_ROLE_USER, 'User'),
    (CHAT_ROLE_ASSISTANT, 'Assistant'),
    (CHAT_ROLE_SYSTEM, 'System'),
)


class ChatHistory(UUIDModel):
    # Un message du chat IA d'un incident, propre à un utilisateur (incident + user).
    incident = models.ForeignKey(
        'Incident', on_delete=models.CASCADE,
        related_name='chat_messages', null=True, blank=True,
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        related_name='chat_messages', null=True, blank=True,
    )
    role = models.CharField(max_length=20, choices=CHAT_ROLES, default=CHAT_ROLE_USER)
    content = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ('created_at', 'id')

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"

class UserAction(UUIDModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=False, null=False)
    action = models.CharField(max_length=255)
    timeStamp = models.DateField(auto_now_add=True)
    # Horodatage précis (le `timeStamp` historique est une date seule) — utilisé par
    # le flux d'activité pour afficher "il y a X min". Nullable pour les lignes existantes.
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ('-created_at', '-timeStamp')

    def __str__(self):
        return self.action
    
class DiscussionMessage(UUIDModel):
    incident = models.ForeignKey('Incident', on_delete=models.CASCADE)
    collaboration = models.ForeignKey(Collaboration, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    # message texte (peut être vide si le message ne contient qu'un audio ou une pièce jointe)
    message = models.TextField(blank=True, null=True)
    audio = models.FileField(upload_to='chat/audio/', storage=VoiceStorage(),
                             blank=True, null=True)
    attachment = models.FileField(
        upload_to='chat/attachments/', storage=DocumentStorage(),
        blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=CHAT_ATTACHMENT_EXTENSIONS)],
        help_text="Pièce jointe : PDF, Word ou Excel uniquement.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_messages", null=True, blank=True)

    def __str__(self):
        return f"Message de {self.sender} le {self.created_at}"

    def clean(self):
        """Au moins un des champs (message, audio, attachment) doit être fourni."""
        from django.core.exceptions import ValidationError
        if not self.message and not self.audio and not self.attachment:
            raise ValidationError("Un message doit contenir du texte, un audio ou une pièce jointe.")


# --- Tâches d'incident (gérées par le leader) ---
class IncidentTask(UUIDModel):
    incident = models.ForeignKey('Incident', related_name='tasks', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField()
    state = models.CharField(max_length=20, choices=TASK_STATES, default=TASK_PENDING)
    proof_image = models.ImageField(upload_to='tasks/proofs/', storage=ImageStorage(),
                                    null=True, blank=True,
                                    help_text="Image de preuve quand la tâche est marquée 'done'.")
    proof_video = models.FileField(upload_to='tasks/proofs/', storage=VideoStorage(),
                                   null=True, blank=True,
                                   help_text="Vidéo de preuve quand la tâche est marquée 'done'.")
    failure_reason = models.TextField(blank=True, null=True,
                                      help_text="Motif d'échec si la tâche est 'failed'.")
    assigned_to = models.ForeignKey(User, related_name='assigned_tasks', null=True, blank=True,
                                    on_delete=models.SET_NULL)
    created_by = models.ForeignKey(User, related_name='created_tasks', on_delete=models.CASCADE)
    is_confirmed = models.BooleanField(
        default=False,
        help_text="True si la tâche a été confirmée par le leader. "
                  "Seules les tâches confirmées comptent dans la progression."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('start_date', 'id')

    def __str__(self):
        return f"Task '{self.title}' (#{self.id}) - {self.state}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError("La date de début doit être antérieure ou égale à la date de fin.")
        if self.state == TASK_DONE and not (self.proof_image or self.proof_video):
            raise ValidationError("Une tâche terminée doit fournir une preuve (image ou vidéo).")
        if self.state == TASK_FAILED and not self.failure_reason:
            raise ValidationError("Une tâche en échec doit avoir un motif renseigné.")

    def _is_creator_leader(self):
        """Vérifie si le créateur de la tâche est le leader de l'incident."""
        if not self.created_by_id:
            return False
        # Le leader est soit via Collaboration(role=leader) soit via incident.taken_by
        if Collaboration.objects.filter(
            incident=self.incident,
            user_id=self.created_by_id,
            role=COLLAB_ROLE_LEADER,
            status='accepted',
        ).exists():
            return True
        return self.incident.taken_by_id == self.created_by_id

    def save(self, *args, **kwargs):
        # Auto-confirmer si créée par le leader
        if not self.pk and not self.is_confirmed:
            if self._is_creator_leader():
                self.is_confirmed = True
        super().save(*args, **kwargs)
        # met à jour la progression de l'incident après chaque sauvegarde
        try:
            self.incident.update_progress()
        except Exception:
            pass

    def delete(self, *args, **kwargs):
        incident = self.incident
        super().delete(*args, **kwargs)
        try:
            incident.update_progress()
        except Exception:
            pass


# --- Suggestions de partenaires (par contributors, validées par le leader) ---
class PartnerSuggestion(UUIDModel):
    incident = models.ForeignKey('Incident', related_name='partner_suggestions', on_delete=models.CASCADE)
    suggested_by = models.ForeignKey(User, related_name='suggestions_made', on_delete=models.CASCADE,
                                     help_text="Contributeur à l'origine de la suggestion.")
    suggested_partner = models.ForeignKey(User, related_name='suggestions_received', on_delete=models.CASCADE,
                                          help_text="Organisation proposée.")
    suggested_role = models.CharField(max_length=20, choices=SUGGESTION_ROLES,
                                      help_text="Rôle proposé (contributor ou observer uniquement).")
    justification = models.TextField(help_text="Court message justifiant la suggestion.")
    status = models.CharField(max_length=20, choices=SUGGESTION_STATUSES, default=SUGGESTION_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("incident", "suggested_partner"),)
        ordering = ('-created_at',)

    def __str__(self):
        return f"Suggestion {self.suggested_partner} ({self.suggested_role}) on {self.incident} - {self.status}"

class OrganisationTag(UUIDModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='incident_preferences')
    incident_type = models.CharField(max_length=255)


class IVRCall(UUIDModel):
    call_sid = models.CharField(max_length=255, unique=True)
    phone_number = models.CharField(max_length=20)
    status = models.CharField(max_length=50, default='initiated')
    zone_selected = models.CharField(max_length=250, blank=True, null=True)
    category_selected = models.ForeignKey('Category', on_delete=models.SET_NULL, null=True, blank=True)
    description_audio_url = models.URLField(blank=True, null=True)
    description_audio_duration = models.IntegerField(blank=True, null=True)
    incident_created = models.ForeignKey('Incident', on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"IVR Call {self.call_sid} - {self.phone_number}"


class IVRInteraction(UUIDModel):
    ivr_call = models.ForeignKey('IVRCall', on_delete=models.CASCADE, related_name='interactions')
    step = models.CharField(max_length=50)
    user_input = models.CharField(max_length=255, blank=True, null=True)
    recording_url = models.URLField(blank=True, null=True)
    recording_duration = models.IntegerField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['timestamp']
    
    def __str__(self):
        return f"{self.ivr_call.call_sid} - {self.step}"  
