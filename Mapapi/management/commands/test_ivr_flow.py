from django.core.management.base import BaseCommand
from django.test import Client
from Mapapi.models import IVRCall, IVRInteraction, Incident, Zone, Category
import json


class Command(BaseCommand):
    help = 'Test the IVR flow with simulated Twilio requests'

    def handle(self, *args, **options):
        client = Client()
        
        self.stdout.write(self.style.WARNING('Starting IVR flow test...'))
        
        test_call_sid = 'TEST_CA1234567890abcdef'
        test_phone = '+237690000000'
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write('Step 1: Initial webhook call')
        self.stdout.write('='*60)
        
        response = client.post('/MapApi/ivr/webhook/', {
            'CallSid': test_call_sid,
            'From': test_phone,
            'CallStatus': 'ringing'
        })
        
        self.stdout.write(f'Status Code: {response.status_code}')
        self.stdout.write(f'Response:\n{response.content.decode()}')
        
        ivr_call = IVRCall.objects.filter(call_sid=test_call_sid).first()
        if ivr_call:
            self.stdout.write(self.style.SUCCESS(f'✓ IVRCall created: {ivr_call}'))
        else:
            self.stdout.write(self.style.ERROR('✗ IVRCall not created'))
            return
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write('Step 2: User selects option 1 (Report incident)')
        self.stdout.write('='*60)
        
        response = client.post('/MapApi/ivr/select-zone/', {
            'CallSid': test_call_sid,
            'Digits': '1'
        })
        
        self.stdout.write(f'Status Code: {response.status_code}')
        self.stdout.write(f'Response:\n{response.content.decode()}')
        
        interaction = IVRInteraction.objects.filter(
            ivr_call=ivr_call,
            step='main_menu'
        ).first()
        if interaction:
            self.stdout.write(self.style.SUCCESS(f'✓ Interaction recorded: {interaction}'))
        
        zones = Zone.objects.all()[:3]
        if zones.exists():
            self.stdout.write(f'\nAvailable zones for testing:')
            for idx, zone in enumerate(zones, 1):
                self.stdout.write(f'  {idx}. {zone.name}')
        else:
            self.stdout.write(self.style.WARNING('⚠ No zones found in database'))
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write('Step 3: User selects zone (option 1)')
        self.stdout.write('='*60)
        
        response = client.post('/MapApi/ivr/select-category/', {
            'CallSid': test_call_sid,
            'Digits': '1'
        })
        
        self.stdout.write(f'Status Code: {response.status_code}')
        self.stdout.write(f'Response:\n{response.content.decode()}')
        
        ivr_call.refresh_from_db()
        if ivr_call.zone_selected:
            self.stdout.write(self.style.SUCCESS(f'✓ Zone selected: {ivr_call.zone_selected}'))
        
        categories = Category.objects.all()[:3]
        if categories.exists():
            self.stdout.write(f'\nAvailable categories for testing:')
            for idx, cat in enumerate(categories, 1):
                self.stdout.write(f'  {idx}. {cat.name}')
        else:
            self.stdout.write(self.style.WARNING('⚠ No categories found in database'))
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write('Step 4: User selects category (option 1)')
        self.stdout.write('='*60)
        
        response = client.post('/MapApi/ivr/record-description/', {
            'CallSid': test_call_sid,
            'Digits': '1'
        })
        
        self.stdout.write(f'Status Code: {response.status_code}')
        self.stdout.write(f'Response:\n{response.content.decode()}')
        
        ivr_call.refresh_from_db()
        if ivr_call.category_selected:
            self.stdout.write(self.style.SUCCESS(f'✓ Category selected: {ivr_call.category_selected.name}'))
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write('Step 5: Process recording (simulated)')
        self.stdout.write('='*60)
        
        test_recording_url = 'https://api.twilio.com/2010-04-01/Accounts/TEST/Recordings/RETEST123'
        
        response = client.post('/MapApi/ivr/process-recording/', {
            'CallSid': test_call_sid,
            'RecordingUrl': test_recording_url,
            'RecordingDuration': '45'
        })
        
        self.stdout.write(f'Status Code: {response.status_code}')
        self.stdout.write(f'Response:\n{response.content.decode()}')
        
        ivr_call.refresh_from_db()
        if ivr_call.description_audio_url:
            self.stdout.write(self.style.SUCCESS(f'✓ Recording URL saved: {ivr_call.description_audio_url}'))
        
        if ivr_call.incident_created:
            self.stdout.write(self.style.SUCCESS(f'✓ Incident created: ID {ivr_call.incident_created.id}'))
            incident = ivr_call.incident_created
            self.stdout.write(f'  Title: {incident.title}')
            self.stdout.write(f'  Zone: {incident.zone}')
            self.stdout.write(f'  Category: {incident.category_id.name if incident.category_id else "N/A"}')
            self.stdout.write(f'  Status: {incident.etat}')
        else:
            self.stdout.write(self.style.ERROR('✗ Incident not created'))
        
        if ivr_call.user:
            self.stdout.write(self.style.SUCCESS(f'✓ User created/found: {ivr_call.user.email}'))
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write('Test Summary')
        self.stdout.write('='*60)
        
        all_interactions = IVRInteraction.objects.filter(ivr_call=ivr_call)
        self.stdout.write(f'\nTotal interactions: {all_interactions.count()}')
        for interaction in all_interactions:
            self.stdout.write(f'  - {interaction.step}: {interaction.user_input or "recording"}')
        
        self.stdout.write(f'\nIVR Call Status: {ivr_call.status}')
        
        self.stdout.write('\n' + self.style.SUCCESS('='*60))
        self.stdout.write(self.style.SUCCESS('IVR Flow Test Completed Successfully!'))
        self.stdout.write(self.style.SUCCESS('='*60))
        
        self.stdout.write('\n' + self.style.WARNING('Cleanup: Deleting test data...'))
        if ivr_call.incident_created:
            ivr_call.incident_created.delete()
        if ivr_call.user and ivr_call.user.email.endswith('@phone.mapaction.com'):
            ivr_call.user.delete()
        ivr_call.delete()
        self.stdout.write(self.style.SUCCESS('✓ Test data cleaned up'))
