from django.utils.deprecation import MiddlewareMixin
from .models import Organisation

class OrganisationFromSubdomainMiddleware(MiddlewareMixin):
    """
    Middleware pour extraire le sous-domaine de la requête et attacher l'organisation à request.organisation
    """
    def process_request(self, request):
        host = request.get_host().split(':')[0]  # retire le port éventuel
        # On suppose que le domaine principal est map-action.com
        # et que le sous-domaine correspond à l'organisation
        parts = host.split('.')
        if len(parts) < 2:
            request.organisation = None
            return
        subdomain = parts[0]
        try:
            organisation = Organisation.objects.get(subdomain=subdomain)
            request.organisation = organisation
        except Organisation.DoesNotExist:
            request.organisation = None
