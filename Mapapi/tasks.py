"""Celery tasks for the Mapapi app.

The main task here is :func:`analyze_incident_with_model_task` which sends an
incident's photo + coordinates to the remote model-deploy service and stores
the structured response on the related :class:`Mapapi.models.Prediction`.
"""
import os
import logging
import mimetypes

import requests
from celery import shared_task
from django.conf import settings

from Mapapi.models import Prediction, PredictionStatus
from Mapapi.services.prediction_mapper import fill_prediction_from_model_response

logger = logging.getLogger(__name__)


def _get_analyze_url():
    return getattr(
        settings,
        "MODEL_DEPLOY_ANALYZE_URL",
        os.getenv("MODEL_DEPLOY_ANALYZE_URL", "http://localhost:8001/api1/analyze/"),
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




