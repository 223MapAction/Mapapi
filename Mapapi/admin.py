from django.contrib import admin
from .models import IVRCall, IVRInteraction


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
