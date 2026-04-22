from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from twilio.twiml.voice_response import VoiceResponse, Gather
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import IVRCall, IVRInteraction, Incident, Category, Zone, User
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class TwilioIVRWebhook(View):
    
    def post(self, request):
        call_sid = request.POST.get('CallSid')
        from_number = request.POST.get('From')
        call_status = request.POST.get('CallStatus')
        
        ivr_call, created = IVRCall.objects.get_or_create(
            call_sid=call_sid,
            defaults={'phone_number': from_number, 'status': call_status}
        )
        
        if not created:
            ivr_call.status = call_status
            ivr_call.save()
        
        response = VoiceResponse()
        response.say(
            "Bienvenue au système de signalement d'incidents de Map Action.",
            language='fr-FR',
            voice='Polly.Celine'
        )
        
        gather = Gather(
            num_digits=1,
            action='/MapApi/ivr/select-zone/',
            method='POST',
            timeout=10
        )
        gather.say(
            "Pour signaler un incident, appuyez sur 1. Pour parler à un opérateur, appuyez sur 2.",
            language='fr-FR',
            voice='Polly.Celine'
        )
        response.append(gather)
        
        response.say(
            "Nous n'avons pas reçu de réponse. Au revoir.",
            language='fr-FR',
            voice='Polly.Celine'
        )
        response.hangup()
        
        return HttpResponse(str(response), content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class SelectZoneView(View):
    
    def post(self, request):
        call_sid = request.POST.get('CallSid')
        digits = request.POST.get('Digits')
        
        try:
            ivr_call = IVRCall.objects.get(call_sid=call_sid)
            IVRInteraction.objects.create(
                ivr_call=ivr_call,
                step='main_menu',
                user_input=digits
            )
        except IVRCall.DoesNotExist:
            logger.error(f"IVRCall not found for CallSid: {call_sid}")
        
        response = VoiceResponse()
        
        if digits == '1':
            zones = Zone.objects.all()[:9]
            
            gather = Gather(
                num_digits=1,
                action='/MapApi/ivr/select-category/',
                method='POST',
                timeout=10
            )
            
            message = "Veuillez sélectionner votre zone. "
            for idx, zone in enumerate(zones, start=1):
                message += f"Pour {zone.name}, appuyez sur {idx}. "
            
            gather.say(message, language='fr-FR', voice='Polly.Celine')
            response.append(gather)
            
            response.say(
                "Nous n'avons pas reçu de réponse. Au revoir.",
                language='fr-FR',
                voice='Polly.Celine'
            )
            response.hangup()
            
        elif digits == '2':
            response.say(
                "Transfert vers un opérateur. Veuillez patienter.",
                language='fr-FR',
                voice='Polly.Celine'
            )
            response.hangup()
        else:
            response.say(
                "Option invalide. Au revoir.",
                language='fr-FR',
                voice='Polly.Celine'
            )
            response.hangup()
        
        return HttpResponse(str(response), content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class SelectCategoryView(View):
    
    def post(self, request):
        call_sid = request.POST.get('CallSid')
        digits = request.POST.get('Digits')
        
        try:
            ivr_call = IVRCall.objects.get(call_sid=call_sid)
            
            zones = Zone.objects.all()[:9]
            zone_index = int(digits) - 1
            
            if 0 <= zone_index < len(zones):
                selected_zone = zones[zone_index]
                ivr_call.zone_selected = selected_zone.name
                ivr_call.save()
                
                IVRInteraction.objects.create(
                    ivr_call=ivr_call,
                    step='zone_selection',
                    user_input=digits
                )
            
        except (IVRCall.DoesNotExist, ValueError, IndexError) as e:
            logger.error(f"Error in SelectCategoryView: {e}")
        
        response = VoiceResponse()
        
        categories = Category.objects.all()[:9]
        
        gather = Gather(
            num_digits=1,
            action='/MapApi/ivr/record-description/',
            method='POST',
            timeout=10
        )
        
        message = "Veuillez sélectionner la catégorie de l'incident. "
        for idx, category in enumerate(categories, start=1):
            message += f"Pour {category.name}, appuyez sur {idx}. "
        
        gather.say(message, language='fr-FR', voice='Polly.Celine')
        response.append(gather)
        
        response.say(
            "Nous n'avons pas reçu de réponse. Au revoir.",
            language='fr-FR',
            voice='Polly.Celine'
        )
        response.hangup()
        
        return HttpResponse(str(response), content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class RecordDescriptionView(View):
    
    def post(self, request):
        call_sid = request.POST.get('CallSid')
        digits = request.POST.get('Digits')
        
        try:
            ivr_call = IVRCall.objects.get(call_sid=call_sid)
            
            categories = Category.objects.all()[:9]
            category_index = int(digits) - 1
            
            if 0 <= category_index < len(categories):
                selected_category = categories[category_index]
                ivr_call.category_selected = selected_category
                ivr_call.save()
                
                IVRInteraction.objects.create(
                    ivr_call=ivr_call,
                    step='category_selection',
                    user_input=digits
                )
            
        except (IVRCall.DoesNotExist, ValueError, IndexError) as e:
            logger.error(f"Error in RecordDescriptionView: {e}")
        
        response = VoiceResponse()
        
        response.say(
            "Veuillez décrire l'incident après le bip. Appuyez sur dièse lorsque vous avez terminé.",
            language='fr-FR',
            voice='Polly.Celine'
        )
        
        response.record(
            action='/MapApi/ivr/process-recording/',
            method='POST',
            max_length=120,
            finish_on_key='#',
            transcribe=False,
            recording_status_callback='/MapApi/ivr/recording-status/',
            recording_status_callback_method='POST'
        )
        
        return HttpResponse(str(response), content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class ProcessRecordingView(View):
    
    def post(self, request):
        call_sid = request.POST.get('CallSid')
        recording_url = request.POST.get('RecordingUrl')
        recording_duration = request.POST.get('RecordingDuration')
        
        try:
            ivr_call = IVRCall.objects.get(call_sid=call_sid)
            ivr_call.description_audio_url = recording_url
            ivr_call.description_audio_duration = recording_duration
            ivr_call.status = 'completed'
            ivr_call.save()
            
            IVRInteraction.objects.create(
                ivr_call=ivr_call,
                step='description_recording',
                recording_url=recording_url,
                recording_duration=recording_duration
            )
            
            user, _ = User.objects.get_or_create(
                phone=ivr_call.phone_number,
                defaults={
                    'email': f"{ivr_call.phone_number}@phone.mapaction.com",
                    'first_name': 'Utilisateur',
                    'last_name': 'Téléphone',
                    'user_type': 'citizen'
                }
            )
            
            incident = Incident.objects.create(
                title=f"Incident signalé par téléphone - {ivr_call.zone_selected}",
                zone=ivr_call.zone_selected or "Zone non spécifiée",
                description=f"Incident signalé via IVR. Enregistrement audio disponible.",
                audio=recording_url,
                user_id=user,
                category_id=ivr_call.category_selected,
                etat='declared'
            )
            
            ivr_call.incident_created = incident
            ivr_call.user = user
            ivr_call.save()
            
        except IVRCall.DoesNotExist:
            logger.error(f"IVRCall not found for CallSid: {call_sid}")
        except Exception as e:
            logger.error(f"Error creating incident from IVR: {e}")
        
        response = VoiceResponse()
        response.say(
            "Merci pour votre signalement. Votre incident a été enregistré avec succès. Au revoir.",
            language='fr-FR',
            voice='Polly.Celine'
        )
        response.hangup()
        
        return HttpResponse(str(response), content_type='text/xml')


@method_decorator(csrf_exempt, name='dispatch')
class RecordingStatusView(View):
    
    def post(self, request):
        call_sid = request.POST.get('CallSid')
        recording_url = request.POST.get('RecordingUrl')
        recording_status = request.POST.get('RecordingStatus')
        
        try:
            ivr_call = IVRCall.objects.get(call_sid=call_sid)
            logger.info(f"Recording status for {call_sid}: {recording_status}, URL: {recording_url}")
            
        except IVRCall.DoesNotExist:
            logger.error(f"IVRCall not found for CallSid: {call_sid}")
        
        return HttpResponse(status=200)


class IVRCallListView(APIView):
    
    def get(self, request):
        ivr_calls = IVRCall.objects.all().order_by('-created_at')
        
        data = []
        for call in ivr_calls:
            data.append({
                'id': call.id,
                'call_sid': call.call_sid,
                'phone_number': call.phone_number,
                'status': call.status,
                'zone_selected': call.zone_selected,
                'category_selected': call.category_selected.name if call.category_selected else None,
                'description_audio_url': call.description_audio_url,
                'description_audio_duration': call.description_audio_duration,
                'incident_id': call.incident_created.id if call.incident_created else None,
                'created_at': call.created_at,
                'updated_at': call.updated_at,
            })
        
        return Response(data, status=status.HTTP_200_OK)


class IVRCallDetailView(APIView):
    
    def get(self, request, call_id):
        try:
            ivr_call = IVRCall.objects.get(id=call_id)
            interactions = ivr_call.interactions.all()
            
            data = {
                'id': ivr_call.id,
                'call_sid': ivr_call.call_sid,
                'phone_number': ivr_call.phone_number,
                'status': ivr_call.status,
                'zone_selected': ivr_call.zone_selected,
                'category_selected': ivr_call.category_selected.name if ivr_call.category_selected else None,
                'description_audio_url': ivr_call.description_audio_url,
                'description_audio_duration': ivr_call.description_audio_duration,
                'incident_id': ivr_call.incident_created.id if ivr_call.incident_created else None,
                'created_at': ivr_call.created_at,
                'updated_at': ivr_call.updated_at,
                'interactions': [
                    {
                        'step': interaction.step,
                        'user_input': interaction.user_input,
                        'recording_url': interaction.recording_url,
                        'recording_duration': interaction.recording_duration,
                        'timestamp': interaction.timestamp
                    }
                    for interaction in interactions
                ]
            }
            
            return Response(data, status=status.HTTP_200_OK)
            
        except IVRCall.DoesNotExist:
            return Response(
                {'error': 'IVR Call not found'},
                status=status.HTTP_404_NOT_FOUND
            )
