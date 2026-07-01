import json

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.core.serializers.json import DjangoJSONEncoder
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import (Collaboration, Notification, User, DiscussionMessage, IncidentTask,
                     UserAction, COLLAB_ROLE_LEADER)


def _actor_label(user):
    org = getattr(getattr(user, 'organisation_member', None), 'name', None)
    return org or (user.get_full_name() or user.email if user else 'Quelqu\'un')
from .Send_mails import send_email
import logging

logger = logging.getLogger(__name__)


def _ws_broadcast(group, payload):
    """Pousse un message vers un groupe WebSocket (depuis un contexte sync).

    Le payload est d'abord normalisé en primitives JSON (UUID -> str, datetime ->
    ISO, etc.) AVANT group_send : la couche Channels sérialise en msgpack, qui ne
    sait pas empaqueter un UUID/datetime. Sans cela, group_send levait
    « can not serialize 'UUID' object », l'exception était avalée ci-dessous, et le
    broadcast était silencieusement perdu (WebSocket ouvert mais aucun message reçu).
    """
    try:
        safe_payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(group, {'type': 'broadcast', 'payload': safe_payload})
    except Exception as exc:  # ne jamais casser une écriture DB à cause du temps réel
        logger.warning("WS broadcast échoué (%s): %s", group, exc)


@receiver(post_save, sender=Notification)
def ws_push_notification(sender, instance, created, **kwargs):
    """Temps réel : pousse chaque notification à son destinataire (qui a fait quoi)."""
    if kwargs.get('raw') or not created:
        return
    _ws_broadcast(f"notifications_{instance.user_id}", {
        'event': 'notification',
        'id': instance.id,
        'type': instance.notif_type,            # catégorie (collaboration_request, …)
        'title': instance.title,                # libellé FR prêt à afficher
        'message': instance.message,
        'incident_title': getattr(getattr(instance, 'incident', None), 'title', None),
        'read': instance.read,
        'colaboration': instance.colaboration_id,
        'incident': instance.incident_id,
        'link': instance.redirect_link(),  # cible de redirection au clic
        'created_at': instance.created_at.isoformat() if instance.created_at else None,
    })


@receiver(post_save, sender=DiscussionMessage)
def ws_push_discussion(sender, instance, created, **kwargs):
    """Temps réel : pousse chaque message de discussion aux membres de l'incident."""
    if kwargs.get('raw') or not created:
        return
    _ws_broadcast(f"discussion_{instance.incident_id}", {
        'event': 'discussion_message',
        'id': instance.id,
        'incident': instance.incident_id,
        'collaboration': instance.collaboration_id,
        'sender': instance.sender_id,
        'message': instance.message,
        'created_at': instance.created_at.isoformat() if instance.created_at else None,
    })


@receiver(post_save, sender=IncidentTask)
def ws_push_task(sender, instance, created, **kwargs):
    """Temps réel : pousse les créations/màj de tâches aux membres de l'incident."""
    if kwargs.get('raw'):
        return
    _ws_broadcast(f"tasks_{instance.incident_id}", {
        'event': 'task_created' if created else 'task_updated',
        'id': instance.id,
        'incident': instance.incident_id,
        'title': instance.title,
        'state': instance.state,
        'assigned_to': instance.assigned_to_id,
        'updated_at': instance.updated_at.isoformat() if getattr(instance, 'updated_at', None) else None,
    })


@receiver(post_delete, sender=IncidentTask)
def ws_push_task_deleted(sender, instance, **kwargs):
    """Temps réel : pousse la SUPPRESSION d'une tâche aux membres de l'incident,
    pour que la carte disparaisse instantanément (et pas seulement au refetch)."""
    if kwargs.get('raw'):
        return
    _ws_broadcast(f"tasks_{instance.incident_id}", {
        'event': 'task_deleted',
        'id': instance.id,
        'incident': instance.incident_id,
    })


@receiver(post_save, sender=UserAction)
def ws_push_activity(sender, instance, created, **kwargs):
    """Temps réel : pousse chaque nouvelle action au flux d'activité global
    (groupe ``activity_feed``). L'ActivityFeedConsumer filtre côté serveur
    l'activité de l'organisation du viewer — comme le REST /activity-feed/ qui
    exclut sa propre organisation."""
    if kwargs.get('raw') or not created:
        return
    u = instance.user
    org = getattr(u, 'organisation_member', None) if u else None
    user_name = (f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email) if u else None
    org_name = org.name if org else None
    _ws_broadcast("activity_feed", {
        'event': 'activity',
        'id': instance.id,
        'action': instance.action,
        'user': u.id if u else None,
        'user_name': user_name,
        'organisation_id': org.id if org else None,
        'organisation_name': org_name,
        'actor': org_name or user_name,   # à afficher en tête (org, repli sur la personne)
        'created_at': instance.created_at.isoformat() if getattr(instance, 'created_at', None) else None,
        'timeStamp': instance.timeStamp.isoformat() if getattr(instance, 'timeStamp', None) else None,
    })


@receiver(pre_save, sender=Collaboration)
def _capture_collab_old_status(sender, instance, **kwargs):
    """Capture l'ancien statut pour détecter accept/decline dans le post_save."""
    if instance.pk:
        instance._old_status = Collaboration.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
    else:
        instance._old_status = None


@receiver(post_save, sender=Collaboration)
def ws_push_collaboration(sender, instance, created, **kwargs):
    """Temps réel : pousse les créations/màj de collaboration à l'émetteur ET au
    leader de l'incident → onglet collaboration + demandes instantanés.
    Groupe ``collaborations_<user_id>`` (cf. CollaborationConsumer)."""
    if kwargs.get('raw'):
        return
    inc = getattr(instance, 'incident', None)
    sender = getattr(instance, 'user', None)
    sender_org = getattr(sender, 'organisation_member', None) if sender else None
    payload = {
        'event': 'collaboration_created' if created else 'collaboration_updated',
        'id': instance.id,
        'incident': instance.incident_id,
        'incident_title': getattr(inc, 'title', None),     # pour afficher sans refetch
        'status': instance.status,
        'role': instance.role,
        'sender': instance.user_id,
        'sender_name': (f"{sender.first_name or ''} {sender.last_name or ''}".strip() or sender.email) if sender else None,
        'sender_organisation': getattr(sender_org, 'name', None),
        'created_at': instance.created_at.isoformat() if getattr(instance, 'created_at', None) else None,
    }
    # Cibles : l'émetteur (sa liste "envoyées") + le leader/récepteur (ses "demandes reçues").
    targets = {instance.user_id}
    leader_id = getattr(getattr(instance, 'incident', None), 'taken_by_id', None)
    if leader_id:
        targets.add(leader_id)
    for uid in targets:
        if uid:
            _ws_broadcast(f"collaborations_{uid}", payload)
    # Journalise l'activité (flux d'activité + journal d'actions).
    try:
        # L'acteur (nom + organisation) est exposé séparément par ActivityFeedSerializer
        # (user_name / organisation_name) ; le texte de l'action ne le répète donc pas.
        incident_title = getattr(getattr(instance, 'incident', None), 'title', None) or "un incident"
        if created:
            UserAction.objects.create(
                user=instance.user,
                action=f"a demandé une collaboration sur l'incident «{incident_title}»."[:255],
            )
        elif getattr(instance, '_old_status', None) != instance.status and instance.status in ('accepted', 'declined'):
            actor = getattr(getattr(instance, 'incident', None), 'taken_by', None) or instance.user
            verbe = "a accepté" if instance.status == 'accepted' else "a refusé"
            UserAction.objects.create(
                user=actor,
                action=f"{verbe} une demande de collaboration sur l'incident «{incident_title}»."[:255],
            )
    except Exception as exc:  # ne jamais casser l'écriture DB
        logger.warning("log activité collaboration échoué: %s", exc)


@receiver(post_save, sender=Collaboration)
def notify_organisation_on_collaboration(sender, instance, created, **kwargs):
    if kwargs.get('raw'):
        return  # chargement de fixtures (loaddata) : ne pas déclencher la logique métier
    if created:
        incident = instance.incident
        user = incident.taken_by
        requesting_user = instance.user
        # La collaboration AUTO-CRÉÉE du LEADER lui-même (lors de la prise en charge,
        # rôle 'leader') n'est PAS une demande d'une autre organisation : on ne notifie
        # pas / on n'envoie pas d'email au leader à propos de sa propre prise en charge
        # (sinon « Bonjour USAD, l'organisation USAD souhaite collaborer… »).
        if user and requesting_user and (
                requesting_user.id == user.id or instance.role == COLLAB_ROLE_LEADER):
            return
        # Nom réel de l'organisation du demandeur (organisation_member) — pas le champ
        # legacy `organisation` souvent vide, qui affichait « L'organisation None ».
        requesting_organisation = (
            getattr(getattr(requesting_user, 'organisation_member', None), 'name', None)
            or requesting_user.organisation or "Une organisation"
        )

        if user and user.email:
            try:
                context = {
                    'incident_id': incident.id,
                    'incident_title': incident.title,  
                    'incident_zone': incident.zone,  
                    'incident_creation_date': incident.created_at,  
                    'organisation': getattr(getattr(user, 'organisation_member', None), 'name', None) or user.organisation,
                    'requesting_organisation': requesting_organisation
                }
                
                # Envoi de l'email à l'organisation
                send_email.delay(
                    subject='Nouvelle demande de collaboration',
                    template_name='emails/collaboration_request.html',
                    context=context,
                    to_email=user.email
                )
                logger.info(f"Email envoyé à {user.email} pour la collaboration sur l'incident {incident.id}.")
                
                # Création de la notification pour l'organisation
                Notification.objects.create(
                    user=user,
                    notif_type='collaboration_request',
                    message=f"L'organisation {requesting_organisation} souhaite collaborer sur l'incident {incident.title} (Zone: {incident.zone}, Date: {incident.created_at.strftime('%d-%m-%Y')})",
                    colaboration=instance,
                    incident=incident,
                )
                logger.info(f"Notification créée pour l'utilisateur {user.email}.")
                
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi de l'email: {str(e)}")
        else:
            logger.error(f"Email non valide ou manquant pour l'utilisateur {user}. Collaboration annulée.")
            instance.delete() 
            
             
def notify_organisations_on_prediction(sender, instance, created, **kwargs):
    if not created:
        return

    incident_type = instance.incident_type

    # Organisations intéressées par ce type d'incident
    matching_orgs = User.objects.filter(
        user_type="elu",
        incident_preferences__incident_type=incident_type
    ).distinct()

    for org in matching_orgs:
        try:
            context = {
                'incident_type': incident_type,
                'prediction_id': instance.id,
                'incident_id': instance.incident_id,
                'organisation': org.elu
            }

            send_email.delay(
                subject=f"[MAP ACTION] Nouveau rapport : {incident_type}",
                template_name='emails/incident_notification.html',
                context=context,
                to_email=org.email
            )

            logger.info(f"Email envoyé à {org.email} pour un nouvel incident de type {incident_type}.")

        except Exception as e:
            logger.error(f"Erreur lors de l'envoi d'une notification à {org.email} : {str(e)}")
