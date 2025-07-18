from django.utils.deprecation import MiddlewareMixin
from .models import Organisation

class OrganisationFromSubdomainMiddleware(MiddlewareMixin):
    """
    Middleware pour extraire le sous-domaine de la requête et attacher l'organisation à request.organisation
    """
    def process_request(self, request):
        subdomain = request.META.get('HTTP_X_TENANT_SUBDOMAIN')
        if not subdomain:
            host = request.get_host().split(':')[0]
            parts = host.split('.')
            subdomain = parts[0] if len(parts) > 2 else None

        if not subdomain:
            request.organisation = None
            return

        try:
            organisation = Organisation.objects.get(subdomain=subdomain)
            request.organisation = organisation
        except Organisation.DoesNotExist:
            request.organisation = None
