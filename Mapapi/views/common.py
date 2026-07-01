"""
Shared helpers used across all views modules.

Imported by each domain view module with:
    from .common import CustomPageNumberPagination, get_random, get_csrf_token, logger
"""
import logging
import random
import string

from django.http import JsonResponse
from django.middleware.csrf import get_token
from rest_framework.pagination import PageNumberPagination


logger = logging.getLogger(__name__)


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000


class IncidentPagination(CustomPageNumberPagination):
    # Défaut adapté à l'onglet incidents (tableau + miniatures). Surchargeable via
    # ?page_size= (ex. ?page_size=12 pour une grille de cartes), plafonné à 100.
    page_size = 20
    max_page_size = 100


class NotificationPagination(CustomPageNumberPagination):
    # Défaut adapté au panneau de notifications. Surchargeable via ?page_size=.
    page_size = 20
    max_page_size = 100


class FieldReportPagination(CustomPageNumberPagination):
    # Petits lots pour un bouton « charger plus » sur les rapports d'agents.
    # Le front charge la page suivante via `next` jusqu'à ce qu'il soit null.
    # Surchargeable via ?page_size= (plafonné à 100).
    page_size = 10
    max_page_size = 100


def get_random(length=7):
    """Generate a random alphanumeric code (default length=7, used for password reset).

    Also supports numeric-only codes by passing a different length/charset if needed
    via the historical helper below.
    """
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def get_random_digits(length=6):
    """Generate a random numeric code (original `get_random(length=6)` behavior)."""
    return ''.join(random.choices(string.digits, k=length))


def get_csrf_token(request):
    csrf_token = get_token(request)
    return JsonResponse({'csrf_token': csrf_token})


# Constant preserved from legacy views.py
N = 7
