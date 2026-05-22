from django.contrib import admin
from .models import (
    IVRCall, IVRInteraction,
    User, Organisation, Incident, Collaboration, DiscussionMessage,
    IncidentTask, PartnerSuggestion, Category, Indicateur, Zone,
    Message, ResponseMessage, Evenement, Communaute, Rapport,
    Notification, FieldReport, IncidentAssignment, PasswordReset, PhoneOTP
)


@admin.register(IVRCall)
class IVRCallAdmin(admin.ModelAdmin):
    list_display = ['call_sid', 'phone_number', 'status', 'zone_selected', 'created_at', 'incident_created']
    list_filter = ['status', 'created_at', 'zone_selected', 'category_selected']
    search_fields = ['call_sid', 'phone_number']
    readonly_fields = ['call_sid', 'created_at', 'updated_at']

    fieldsets = (
        ('Informations d\'appel', {
            'fields': ('call_sid', 'phone_number', 'status')
        }),
        ('Données collectées', {
            'fields': ('zone_selected', 'category_selected', 'description_audio_url', 'description_audio_duration')
        }),
        ('Résultat', {
            'fields': ('incident_created', 'user')
        }),
        ('Horodatage', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def has_add_permission(self, request):
        return False


@admin.register(IVRInteraction)
class IVRInteractionAdmin(admin.ModelAdmin):
    list_display = ['ivr_call', 'step', 'user_input', 'timestamp']
    list_filter = ['step', 'timestamp']
    search_fields = ['ivr_call__call_sid', 'ivr_call__phone_number']
    readonly_fields = ['timestamp']

    def has_add_permission(self, request):
        return False


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'user_type', 'org_role', 'is_staff', 'is_active', 'date_joined']
    list_filter = ['user_type', 'org_role', 'is_staff', 'is_active', 'date_joined']
    search_fields = ['email', 'first_name', 'last_name', 'organisation', 'agent_code']
    readonly_fields = ['date_joined', 'verification_token', 'otp', 'otp_expiration']
    fieldsets = (
        ('Informations personnelles', {
            'fields': ('email', 'first_name', 'last_name', 'phone', 'address', 'organisation', 'organisation_member')
        }),
        ('Rôles et permissions', {
            'fields': ('user_type', 'org_role', 'is_staff', 'is_superuser', 'is_active', 'is_verified')
        }),
        ('Authentification', {
            'fields': ('password', 'agent_code', 'pin_code', 'must_change_pin', 'otp', 'otp_expiration')
        }),
        ('Vérification', {
            'fields': ('verification_token',)
        }),
        ('Métadonnées', {
            'fields': ('date_joined', 'is_deleted')
        }),
    )


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ['name', 'acronym', 'organisation_type', 'activity_sector', 'intervention_country', 'partner_status', 'created_at']
    list_filter = ['organisation_type', 'activity_sector', 'intervention_country', 'partner_status', 'is_premium']
    search_fields = ['name', 'acronym', 'description', 'phone', 'website_url']
    readonly_fields = ['created_at']


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'zone', 'etat', 'progress', 'is_public', 'is_deleted', 'created_at', 'taken_by']
    list_filter = ['etat', 'is_public', 'is_deleted', 'created_at', 'category_id']
    search_fields = ['title', 'zone', 'description']
    readonly_fields = ['created_at', 'progress']
    fieldsets = (
        ('Informations de base', {
            'fields': ('title', 'zone', 'description', 'etat', 'category_id', 'indicateur_id')
        }),
        ('Médias', {
            'fields': ('photo', 'video', 'audio')
        }),
        ('Localisation', {
            'fields': ('lattitude', 'longitude')
        }),
        ('Gestion', {
            'fields': ('user_id', 'taken_by', 'is_public', 'is_deleted')
        }),
        ('Résolution', {
            'fields': ('resolution_start_date', 'resolution_end_date', 'progress')
        }),
        ('Métadonnées', {
            'fields': ('slug', 'created_at')
        }),
    )


@admin.register(Collaboration)
class CollaborationAdmin(admin.ModelAdmin):
    list_display = ['id', 'incident', 'user', 'role', 'status', 'created_at']
    list_filter = ['role', 'status', 'created_at']
    search_fields = ['user__email', 'incident__title']
    readonly_fields = ['created_at']


@admin.register(DiscussionMessage)
class DiscussionMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'incident', 'sender', 'recipient', 'created_at']
    list_filter = ['created_at']
    search_fields = ['message', 'sender__email', 'recipient__email']
    readonly_fields = ['created_at']


@admin.register(IncidentTask)
class IncidentTaskAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'incident', 'state', 'start_date', 'end_date', 'created_by']
    list_filter = ['state', 'start_date', 'end_date', 'created_at']
    search_fields = ['title', 'description', 'incident__title']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PartnerSuggestion)
class PartnerSuggestionAdmin(admin.ModelAdmin):
    list_display = ['id', 'incident', 'suggested_by', 'suggested_partner', 'suggested_role', 'status', 'created_at']
    list_filter = ['suggested_role', 'status', 'created_at']
    search_fields = ['justification', 'suggested_partner__email', 'incident__title']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at']


@admin.register(Indicateur)
class IndicateurAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at']


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'objet', 'user_id', 'communaute', 'created_at']
    list_filter = ['created_at']
    search_fields = ['objet', 'description']
    readonly_fields = ['created_at']


@admin.register(ResponseMessage)
class ResponseMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'response', 'message', 'elu', 'created_at']
    list_filter = ['created_at']
    search_fields = ['response']
    readonly_fields = ['created_at']


@admin.register(Evenement)
class EvenementAdmin(admin.ModelAdmin):
    list_display = ['title', 'zone', 'date', 'created_at']
    list_filter = ['date', 'created_at']
    search_fields = ['title', 'zone', 'description']
    readonly_fields = ['created_at']


@admin.register(Communaute)
class CommunauteAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at']


@admin.register(Rapport)
class RapportAdmin(admin.ModelAdmin):
    list_display = ['id', 'details', 'zone', 'statut', 'created_at']
    list_filter = ['statut', 'disponible', 'created_at']
    search_fields = ['details', 'zone', 'type']
    readonly_fields = ['created_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'message', 'read', 'created_at']
    list_filter = ['read', 'created_at']
    search_fields = ['message', 'user__email']
    readonly_fields = ['created_at']


@admin.register(FieldReport)
class FieldReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'incident', 'agent', 'visited_at', 'created_at']
    list_filter = ['visited_at', 'created_at']
    search_fields = ['incident__title', 'agent__email']
    readonly_fields = ['created_at']


@admin.register(IncidentAssignment)
class IncidentAssignmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'incident', 'agent', 'assigned_by', 'deadline', 'status', 'created_at']
    list_filter = ['status', 'deadline', 'created_at']
    search_fields = ['incident__title', 'agent__email', 'assigned_by__email']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PasswordReset)
class PasswordResetAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'code', 'used', 'date_created', 'date_used']
    list_filter = ['used', 'date_created', 'date_used']
    search_fields = ['code', 'user__email']
    readonly_fields = ['date_created', 'date_used']


@admin.register(PhoneOTP)
class PhoneOTPAdmin(admin.ModelAdmin):
    list_display = ['id', 'phone_number', 'otp_code', 'created_at']
    list_filter = ['created_at']
    search_fields = ['phone_number', 'otp_code']
    readonly_fields = ['created_at']
