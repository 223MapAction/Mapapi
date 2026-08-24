from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import logging
logger = logging.getLogger(__name__)


@shared_task
def send_email(subject, template_name, context, to_email):
    logger.info("Début de l'envoi d'un e-mail (template=%s)", template_name)
    try:
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)
        from_email = settings.DEFAULT_FROM_EMAIL or 'Map Action <contact@map-action.com>'
        msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        logger.info("E-mail envoyé avec succès")
    except Exception:
        logger.exception("Échec de l'envoi de l'e-mail")
        raise


@shared_task
def send_sms_task(phone_number, otp_code, custom_message=None):
    logger.info("Début de l'envoi d'un SMS")
    try:
        from Mapapi.views.user import send_sms
        result = send_sms(phone_number, otp_code, custom_message)
        if result:
            logger.info("SMS envoyé avec succès")
        else:
            logger.error("Échec de l'envoi du SMS")
    except Exception:
        logger.exception("Erreur inattendue lors de l'envoi du SMS")
        raise
