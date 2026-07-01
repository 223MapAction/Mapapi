"""Celery tasks for the Mapapi app.

The main task here is :func:`analyze_incident_with_model_task` which sends an
incident's photo + coordinates to the remote model-deploy service and stores
the structured response on the related :class:`Mapapi.models.Prediction`.
"""
import os
import logging
import mimetypes
from datetime import timedelta

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from Mapapi.models import (
    Prediction, PredictionStatus, Incident, Collaboration, Notification,
    IN_VALIDATION, RESOLVED_DEFINITIVE, TAKEN, DECLARED,
    COLLAB_STATUS_ACCEPTED, COLLAB_STATUS_TERMINATED,
    IncidentOrgAssignment, ORG_ASSIGNMENT_PENDING, ORG_ASSIGNMENT_ACCEPTED,
    ORG_ROLE_ADMIN, ANTI_GEL_DEADLINE_DAYS,
)
from Mapapi.services.prediction_mapper import fill_prediction_from_model_response

logger = logging.getLogger(__name__)

# Anti-gel (spec T3) : délai de repli quand la sévérité de l'Incident est nulle/inconnue.
# La spec prévoit Élevée 30 j / Moyenne 60 j / Faible 90 j (cf. Incident.severity et
# ANTI_GEL_DEADLINE_DAYS dans models.py). Faute de sévérité exploitable, on applique 60 j.
ANTI_GEL_DEFAULT_DAYS = 60


def _antigel_deadline_days(incident):
    """Délai anti-gel (en jours) pour `incident` selon sa sévérité.

    Repli sur ANTI_GEL_DEFAULT_DAYS (60 j) si la sévérité est nulle/inconnue.
    """
    return ANTI_GEL_DEADLINE_DAYS.get(incident.severity, ANTI_GEL_DEFAULT_DAYS)


def _get_analyze_url():
    return getattr(
        settings,
        "MODEL_DEPLOY_ANALYZE_URL",
        os.getenv("MODEL_DEPLOY_ANALYZE_URL", "http://localhost:8001/analyze/upload"),
    )


def _get_timeout():
    return int(getattr(
        settings,
        "MODEL_DEPLOY_TIMEOUT",
        os.getenv("MODEL_DEPLOY_TIMEOUT", 180),
    ))


@shared_task(
    bind=True,
    autoretry_for=(requests.exceptions.RequestException,),
    retry_kwargs={"max_retries": 3, "countdown": 30},
    retry_backoff=True,
)
def analyze_incident_with_model_task(self, prediction_id):
    """Send the incident photo to the model-deploy service and store the result.

    This task is idempotent: if the prediction is already COMPLETED, it
    returns early. Failures are persisted on the Prediction (status=FAILED,
    error_message=...) and re-raised so that Celery can retry where relevant.
    """
    prediction = Prediction.objects.select_related("incident").get(id=prediction_id)
    incident = prediction.incident

    if prediction.status in (
        PredictionStatus.COMPLETED,
        PredictionStatus.COMPLETED_WITH_WARNING,
    ):
        return {"skipped": True, "reason": "already completed"}

    if incident is None:
        prediction.status = PredictionStatus.FAILED
        prediction.error_message = "Prediction has no related incident."
        prediction.save(update_fields=["status", "error_message", "updated_at"])
        return

    if not incident.photo:
        prediction.status = PredictionStatus.FAILED
        prediction.error_message = "Incident has no photo."
        prediction.save(update_fields=["status", "error_message", "updated_at"])
        return

    prediction.status = PredictionStatus.PROCESSING
    prediction.error_message = ""
    prediction.save(update_fields=["status", "error_message", "updated_at"])

    analyze_url = _get_analyze_url()
    timeout = _get_timeout()

    try:
        # Use the field's own storage (Supabase via ImageStorage) instead of
        # the global default_storage, otherwise the worker tries to read from
        # the local filesystem and fails with FileNotFoundError.
        photo_name = incident.photo.name
        filename = os.path.basename(photo_name)
        content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"

        image_file = incident.photo.storage.open(photo_name, "rb")
        try:
            files = {"image": (filename, image_file, content_type)}
            data = {
                "latitude": str(incident.lattitude) if incident.lattitude is not None else "",
                "longitude": str(incident.longitude) if incident.longitude is not None else "",
                "incident_id": str(incident.pk),
            }

            logger.info(
                "Calling model-deploy %s for incident=%s photo=%s",
                analyze_url, incident.pk, photo_name,
            )
            response = requests.post(
                analyze_url,
                files=files,
                data=data,
                timeout=timeout,
            )
        finally:
            try:
                image_file.close()
            except Exception:
                pass

        response.raise_for_status()
        result = response.json()

        fill_prediction_from_model_response(prediction, result)
        return {"prediction_id": prediction.id, "status": prediction.status}

    except requests.exceptions.RequestException as exc:
        prediction.status = PredictionStatus.FAILED
        prediction.error_message = f"Model service request failed: {exc}"
        prediction.save(update_fields=["status", "error_message", "updated_at"])
        raise

    except Exception as exc:  # noqa: BLE001
        prediction.status = PredictionStatus.FAILED
        prediction.error_message = str(exc)
        prediction.save(update_fields=["status", "error_message", "updated_at"])
        raise


# ============================================================================
# Phase 4 — mécanismes temporels du cycle de vie de l'incident (Celery Beat)
# Tâches idempotentes : sûres à rejouer ; n'agissent que sur les lignes éligibles.
# ============================================================================

@shared_task
def auto_validate_overdue_resolutions():
    """Validation tacite à 72 h (spec D1).

    Tout incident en 'in_validation' dont validation_deadline est dépassée passe
    automatiquement en 'resolved_definitive' (le Super Admin n'a pas tranché à temps).
    Idempotent : ne sélectionne que les lignes encore 'in_validation' avec une
    échéance passée ; une fois basculées, elles ne ressortent plus.
    """
    now = timezone.now()
    qs = Incident.objects.filter(
        etat=IN_VALIDATION,
        validation_deadline__isnull=False,
        validation_deadline__lt=now,
    )
    count = 0
    for incident in qs:
        incident.etat = RESOLVED_DEFINITIVE
        incident.save(update_fields=['etat'])
        # Spec §5 : à la résolution définitive, les collaborations encore actives
        # passent en « Terminée ». Idempotent (ne touche que les 'accepted').
        Collaboration.objects.filter(
            incident=incident,
            status=COLLAB_STATUS_ACCEPTED,
        ).update(status=COLLAB_STATUS_TERMINATED)
        count += 1
        logger.info(
            "auto_validate_overdue_resolutions: incident=%s validé tacitement "
            "(deadline=%s) -> resolved_definitive",
            incident.pk, incident.validation_deadline,
        )
    return {"validated": count}


@shared_task
def revert_stale_taken_incidents():
    """Anti-gel / délai d'échec de prise en compte (spec T3 / §5).

    Pour chaque incident 'taken_into_account' avec taken_in_charge_at non nul, on
    calcule le délai (deadline) selon sa sévérité — Élevée 30 j / Moyenne 60 j /
    Faible 90 j ; repli ANTI_GEL_DEFAULT_DAYS (60 j) si nulle/inconnue — et l'écoulé
    (elapsed = now - taken_in_charge_at) :

    - elapsed >= deadline       -> retour en 'declared' (champs de prise en charge
                                   remis à zéro), drapeaux d'avertissement réarmés.
    - elapsed >= 0.90*deadline  -> avertissement au leader (taken_by) à 90 %, une
                                   seule fois (antigel_warned_90, + 75 par sûreté).
    - elapsed >= 0.75*deadline  -> avertissement au leader (taken_by) à 75 %, une
                                   seule fois (antigel_warned_75).

    Avertissements : même schéma que ReportToAdminView (Notification au leader,
    colaboration=None, message tronqué à 255 car.). Si taken_by est nul, on saute
    la Notification mais on positionne quand même le drapeau (pas de re-déclenchement).

    On exige taken_in_charge_at non nul : les incidents pris en compte AVANT l'ajout
    de ce champ (timestamp nul) ne sont jamais traités (pas de date fiable).
    Idempotent : un incident repassé 'declared' ne ressort plus ; un avertissement
    déjà émis (drapeau posé) ne se redéclenche pas.
    """
    now = timezone.now()
    qs = Incident.objects.filter(
        etat=TAKEN,
        taken_in_charge_at__isnull=False,
    )
    reverted = 0
    warned_75 = 0
    warned_90 = 0
    for incident in qs:
        deadline_days = _antigel_deadline_days(incident)
        elapsed = now - incident.taken_in_charge_at
        deadline = timedelta(days=deadline_days)

        if elapsed >= deadline:
            incident.etat = DECLARED
            incident.taken_by = None
            incident.take_in_charge_mode = None
            incident.taken_in_charge_at = None
            incident.antigel_warned_75 = False
            incident.antigel_warned_90 = False
            incident.save(update_fields=[
                'etat', 'taken_by', 'take_in_charge_mode', 'taken_in_charge_at',
                'antigel_warned_75', 'antigel_warned_90',
            ])
            reverted += 1
            logger.info(
                "revert_stale_taken_incidents: incident=%s gelé > %s j -> declared "
                "(anti-gel, spec T3)",
                incident.pk, deadline_days,
            )

        elif elapsed >= 0.90 * deadline and not incident.antigel_warned_90:
            _notify_antigel_leader(incident, 90, deadline_days)
            # Poser aussi 75 pour ne pas déclencher l'avertissement à 75 % en retard.
            incident.antigel_warned_90 = True
            incident.antigel_warned_75 = True
            incident.save(update_fields=['antigel_warned_90', 'antigel_warned_75'])
            warned_90 += 1

        elif elapsed >= 0.75 * deadline and not incident.antigel_warned_75:
            _notify_antigel_leader(incident, 75, deadline_days)
            incident.antigel_warned_75 = True
            incident.save(update_fields=['antigel_warned_75'])
            warned_75 += 1

    return {"reverted": reverted, "warned_75": warned_75, "warned_90": warned_90}


def _notify_antigel_leader(incident, pct, deadline_days):
    """Notifie le leader (incident.taken_by) qu'un seuil anti-gel est atteint.

    Même schéma que ReportToAdminView : Notification(user=leader, colaboration=None,
    message tronqué à 255 car.). Sans leader (taken_by nul), on ne crée rien (le
    drapeau est posé par l'appelant pour éviter tout re-déclenchement).
    """
    leader = incident.taken_by
    if leader is None:
        return
    titre = incident.title or incident.zone
    message = (
        f"Anti-gel : l'incident « {titre} » a atteint {pct} % "
        f"du délai de prise en compte ({deadline_days} j). Agissez pour éviter "
        f"son retour automatique en « Déclaré »."
    )[:255]
    Notification.objects.create(user=leader, notif_type='deadline_warning',
                                message=message, colaboration=None, incident=incident)


@shared_task
def purge_expired_trash():
    """Purge de la Corbeille à 30 j (spec D10).

    Suppression DÉFINITIVE (.delete()) des incidents en corbeille (is_deleted=True)
    dont la mise en corbeille (deleted_at) date de plus de 30 jours. Les
    suppressions antérieures à l'ajout de deleted_at (timestamp nul) ne sont PAS
    purgées — on ne supprime que ce qu'on peut dater de façon fiable.
    Idempotent : les lignes purgées disparaissent ; relancer ne refait rien.
    """
    cutoff = timezone.now() - timedelta(days=30)
    qs = Incident.objects.filter(
        is_deleted=True,
        deleted_at__isnull=False,
        deleted_at__lt=cutoff,
    )
    purged_ids = list(qs.values_list('pk', flat=True))
    count = 0
    with transaction.atomic():
        for incident in qs:
            incident.delete()
            count += 1
            logger.info(
                "purge_expired_trash: incident=%s purgé définitivement "
                "(deleted_at antérieur à %s)",
                incident.pk, cutoff,
            )
    return {"purged": count, "ids": purged_ids}


@shared_task
def auto_accept_overdue_assignments():
    """Acceptation tacite des assignations d'organisation à 72 h (spec D4).

    Toute IncidentOrgAssignment 'pending' dont la deadline est dépassée passe
    automatiquement en 'accepted' (l'Admin de l'organisation cible n'a pas
    répondu à temps), avec responded_at = maintenant, et l'incident est engagé
    comme dans l'endpoint accept ('declared' → 'taken_into_account', taken_by +
    taken_in_charge_at). taken_by est fixé à un Admin de l'organisation s'il en
    existe un (l'org engage via l'un de ses Admins). Idempotent : ne sélectionne
    que les lignes encore 'pending' avec une échéance passée.
    """
    now = timezone.now()
    qs = IncidentOrgAssignment.objects.select_related(
        'incident', 'organisation'
    ).filter(
        status=ORG_ASSIGNMENT_PENDING,
        deadline__lt=now,
    )
    count = 0
    for assignment in qs:
        assignment.status = ORG_ASSIGNMENT_ACCEPTED
        assignment.responded_at = now
        assignment.save(update_fields=['status', 'responded_at'])

        # Engager l'incident : taken_by = un Admin de l'org cible si disponible.
        org_admin = assignment.organisation.members.filter(
            org_role=ORG_ROLE_ADMIN
        ).first()
        incident = assignment.incident
        if incident.etat == DECLARED:
            incident.etat = TAKEN
            incident.taken_by = org_admin
            incident.taken_in_charge_at = now
            incident.save(update_fields=['etat', 'taken_by', 'taken_in_charge_at'])

        count += 1
        logger.info(
            "auto_accept_overdue_assignments: assignation=%s acceptée tacitement "
            "(deadline=%s) -> incident %s engagé",
            assignment.pk, assignment.deadline, incident.pk,
        )
    return {"accepted": count}


# --- Legacy code, kept for reference -----------------------------------------
# from celery import shared_task
# from django_http_exceptions import HTTPExceptions
# from .models import *
# import json
# import requests
# import overpy

# @shared_task
# def OverpassCall(lat, lon):
    
#     query = f"""
#         [out:json];
#         (
#             node["amenity"="school"](around:500, {lat}, {lon});
#             node["amenity"="river"](around:500, {lat}, {lon});
#             node["amenity"="marigot"](around:500, {lat}, {lon});
#             node["amenity"="clinic"](around:500, {lat}, {lon});
#         );
#         out body;
#         >;
#         out skel qt;
#         """
#     api = overpy.Overpass()
#     result = api.query(query)
#     results_list = []
#     for node in result.nodes:
#         result_item = {
#             "amenity": node.tags.get("amenity", ""),
#             "name": node.tags.get("name", ""),
                
#         }
#         results_list.append(result_item)
    
            
#     return results_list


# @shared_task
# def prediction_task(image_name, longitude, latitude, incident_id, sensitive_structures):
    
#     sensitive_structures_names = []

#     for entry in sensitive_structures:
#         if entry['amenity'] == "school":
#             sensitive_structures_names.append('ecole')
#         elif entry['amenity'] == "river":
#             sensitive_structures_names.append("cours d'eau")
#         elif entry['amenity'] == "marigot":
#             sensitive_structures_names.append('marigot')
#         elif entry['amenity'] == "clinic":
#             sensitive_structures_names.append('clinique')

#     print(sensitive_structures_names)
    
#     fastapi_url = "http://51.159.141.113:8001/api1/image/predict"
    
#     payload = {"image_name": image_name, "sensitive_structures": sensitive_structures_names, "incident_id": str(incident_id)}
#     longitude = longitude
    
#     response = requests.post(fastapi_url, json=payload)
    
#     if response.status_code != 200:
#         raise HTTPExceptions.INTERNAL_SERVER_ERROR
    
#     result = response.json()
#     prediction = result["prediction"]
#     context = result["context"]
#     in_depth = result["in_depht"]
#     piste_solution = result["piste_solution"]

    
    
#     return prediction, longitude, context, in_depth, piste_solution




