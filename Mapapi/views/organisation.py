"""Organisation & tenant-config endpoints."""
from rest_framework import status, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from ..models import Organisation
from ..serializer import OrganisationSerializer


class OrganisationViewSet(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = Organisation.objects.all()
    serializer_class = OrganisationSerializer
    permission_classes = []

    def get_queryset(self):
        # Optionnel : filtrer selon les droits de l'utilisateur
        return Organisation.objects.all()

class TenantConfigView(APIView):
    permission_classes = []  # Accessible sans authentification, car utilisé pour personnaliser le front dès le login

    def get(self, request, format=None):
        org = getattr(request, 'organisation', None)
        if org is None:
            return Response({'detail': 'Organisation not found for this subdomain.'}, status=status.HTTP_404_NOT_FOUND)
        data = {
            'name': org.name,
            'subdomain': org.subdomain,
            'logo_url': org.logo_url,
            'primary_color': org.primary_color,
            'secondary_color': org.secondary_color,
            'background_color': org.background_color,
            'is_premium': org.is_premium,
        }
        return Response(data)
