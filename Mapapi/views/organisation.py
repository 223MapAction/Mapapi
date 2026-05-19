"""Organisation & tenant-config endpoints + member management."""
import string
import random

from rest_framework import status, generics, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from ..models import Organisation, User, ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD
from ..serializer import OrganisationSerializer, OrganisationMemberSerializer


class OrganisationViewSet(generics.ListCreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = Organisation.objects.all()
    serializer_class = OrganisationSerializer
    permission_classes = []

    def get_queryset(self):
        return Organisation.objects.all()


class TenantConfigView(APIView):
    permission_classes = []

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


@extend_schema(
    description="Liste les membres d'une organisation. Réservé aux admins et agents de bureau de l'org.",
    responses={200: OrganisationMemberSerializer(many=True)},
)
class OrganisationMemberListView(generics.ListAPIView):
    """GET /organisations/<pk>/members/ — liste des membres de l'organisation."""
    serializer_class = OrganisationMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        org_id = self.kwargs['pk']
        return User.objects.filter(organisation_member_id=org_id).order_by('org_role', 'last_name')

    def list(self, request, *args, **kwargs):
        # Vérifier que l'utilisateur est admin ou agent de bureau de cette org
        org_id = self.kwargs['pk']
        user = request.user
        if not (user.is_staff or (
            user.organisation_member_id == org_id
            and user.org_role in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]
        )):
            return Response(
                {"error": "Vous n'avez pas les droits pour voir les membres de cette organisation."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().list(request, *args, **kwargs)


@extend_schema(
    description="Ajouter un membre à une organisation. Génère un agent_code si le rôle est field_agent.",
    request=OrganisationMemberSerializer,
    responses={201: OrganisationMemberSerializer},
)
class OrganisationMemberCreateView(APIView):
    """POST /organisations/<pk>/members/ — ajouter un membre."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        # Seul un admin org ou agent de bureau de cette org peut ajouter
        if not (user.is_staff or (
            user.organisation_member_id == pk
            and user.org_role in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]
        )):
            return Response(
                {"error": "Vous n'avez pas les droits pour gérer les membres."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            org = Organisation.objects.get(pk=pk)
        except Organisation.DoesNotExist:
            return Response({"error": "Organisation non trouvée."}, status=status.HTTP_404_NOT_FOUND)

        user_id = request.data.get('user_id')
        org_role = request.data.get('org_role')

        if not user_id or not org_role:
            return Response(
                {"error": "user_id et org_role sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if org_role not in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD]:
            return Response(
                {"error": f"Rôle invalide. Choix : org_admin, bureau_agent, field_agent."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            member = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"error": "Utilisateur non trouvé."}, status=status.HTTP_404_NOT_FOUND)

        # Affecter à l'organisation
        member.organisation_member = org
        member.org_role = org_role

        # Générer un code agent si c'est un agent de terrain
        if org_role == ORG_ROLE_FIELD and not member.agent_code:
            member.generate_agent_code()

        member.save()

        serializer = OrganisationMemberSerializer(member)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    description="Modifier le rôle ou retirer un membre d'une organisation.",
    responses={200: OrganisationMemberSerializer},
)
class OrganisationMemberDetailView(APIView):
    """
    PATCH  /organisations/<pk>/members/<user_id>/ — modifier le rôle
    DELETE /organisations/<pk>/members/<user_id>/ — retirer de l'org
    """
    permission_classes = [IsAuthenticated]

    def _check_permission(self, request, pk):
        user = request.user
        if user.is_staff:
            return True
        return (
            user.organisation_member_id == pk
            and user.org_role in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU]
        )

    def patch(self, request, pk, user_id):
        if not self._check_permission(request, pk):
            return Response(
                {"error": "Droits insuffisants."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            member = User.objects.get(pk=user_id, organisation_member_id=pk)
        except User.DoesNotExist:
            return Response({"error": "Membre non trouvé dans cette organisation."}, status=status.HTTP_404_NOT_FOUND)

        new_role = request.data.get('org_role')
        if new_role:
            if new_role not in [ORG_ROLE_ADMIN, ORG_ROLE_BUREAU, ORG_ROLE_FIELD]:
                return Response({"error": "Rôle invalide."}, status=status.HTTP_400_BAD_REQUEST)
            member.org_role = new_role
            # Générer code agent si nouveau rôle terrain
            if new_role == ORG_ROLE_FIELD and not member.agent_code:
                member.generate_agent_code()
            member.save()

        serializer = OrganisationMemberSerializer(member)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, user_id):
        if not self._check_permission(request, pk):
            return Response(
                {"error": "Droits insuffisants."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            member = User.objects.get(pk=user_id, organisation_member_id=pk)
        except User.DoesNotExist:
            return Response({"error": "Membre non trouvé dans cette organisation."}, status=status.HTTP_404_NOT_FOUND)

        member.organisation_member = None
        member.org_role = None
        member.save(update_fields=['organisation_member', 'org_role'])

        return Response({"message": "Membre retiré de l'organisation."}, status=status.HTTP_200_OK)
