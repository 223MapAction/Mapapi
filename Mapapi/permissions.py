"""Permissions custom liées à la collaboration sur un incident.

Ces permissions s'appuient sur le modèle suivant :
  - `Incident.taken_by` désigne le leader (User / organisation) ;
  - `Collaboration(user, incident, role)` matérialise la relation entre
    une organisation et un incident, avec un rôle (leader/contributor/observer)
    et un `status` (pending/accepted/declined).

"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import (
    Collaboration,
    Incident,
    COLLAB_ROLE_LEADER,
    COLLAB_ROLE_CONTRIBUTOR,
    COLLAB_ROLE_OBSERVER,
)


def _get_incident_from_view(view, request):
    """Récupère l'incident ciblé par la vue.

    Par convention :
      - `view.kwargs['incident_id']` si présent ;
      - sinon `request.data.get('incident')` ;
      - sinon `obj.incident` (utilisé dans has_object_permission).
    """
    incident_id = view.kwargs.get('incident_id') or view.kwargs.get('pk')
    if incident_id:
        try:
            return Incident.objects.get(pk=incident_id)
        except (Incident.DoesNotExist, ValueError, TypeError):
            return None
    return None


class IsIncidentLeader(BasePermission):
    """Autorise uniquement le leader de l'incident.
    Le leader est déterminé par une Collaboration acceptée de rôle 'leader',
    ou par défaut le premier utilisateur qui a pris en charge l'incident (taken_by).
    """

    message = "Seul le leader de l'incident peut effectuer cette action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        incident = _get_incident_from_view(view, request)
        if incident is None:
            # si pas d'incident dans l'URL, on délègue à has_object_permission
            return True
        if Collaboration.objects.filter(
            incident=incident,
            user=request.user,
            role=COLLAB_ROLE_LEADER,
            status='accepted'
        ).exists():
            return True
        return incident.taken_by_id == request.user.id

    def has_object_permission(self, request, view, obj):
        incident = getattr(obj, 'incident', obj if isinstance(obj, Incident) else None)
        if incident is None:
            return False
        if Collaboration.objects.filter(
            incident=incident,
            user=request.user,
            role=COLLAB_ROLE_LEADER,
            status='accepted'
        ).exists():
            return True
        return incident.taken_by_id == request.user.id


class IsIncidentCollaborator(BasePermission):
    """Autorise tout membre (leader, contributor, observer) avec status='accepted'."""

    message = "Vous n'êtes pas membre de la collaboration sur cet incident."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        incident = _get_incident_from_view(view, request)
        if incident is None:
            return True
        if incident.taken_by_id == request.user.id:
            return True
        return Collaboration.objects.filter(
            incident=incident, user=request.user, status='accepted'
        ).exists()

    def has_object_permission(self, request, view, obj):
        incident = getattr(obj, 'incident', obj if isinstance(obj, Incident) else None)
        if incident is None:
            return False
        if incident.taken_by_id == request.user.id:
            return True
        return Collaboration.objects.filter(
            incident=incident, user=request.user, status='accepted'
        ).exists()


class IsIncidentContributor(BasePermission):
    """Autorise uniquement les contributeurs (role=contributor, status=accepted).

    Utilisé pour les suggestions de partenaires, qui ne peuvent être émises
    que par un contributeur.
    """

    message = "Seul un contributeur peut effectuer cette action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Les méthodes de lecture restent autorisées pour tous les collaborateurs
        if request.method in SAFE_METHODS:
            return IsIncidentCollaborator().has_permission(request, view)
        incident = _get_incident_from_view(view, request)
        if incident is None:
            return True
        return Collaboration.objects.filter(
            incident=incident,
            user=request.user,
            role=COLLAB_ROLE_CONTRIBUTOR,
            status='accepted',
        ).exists()


class IsIncidentLeaderOrContributor(BasePermission):
    """Autorise le leader de l'incident OU un contributeur accepté.

    Utilisé pour les suggestions de partenaires : aujourd'hui un leader peut
    également suggérer des partenaires (en plus des contributeurs).
    """

    message = "Seul le leader ou un contributeur peut effectuer cette action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return IsIncidentCollaborator().has_permission(request, view)
        incident = _get_incident_from_view(view, request)
        if incident is None:
            return True
        if incident.taken_by_id == request.user.id:
            return True
        return Collaboration.objects.filter(
            incident=incident,
            user=request.user,
            role=COLLAB_ROLE_CONTRIBUTOR,
            status='accepted',
        ).exists()


class IsIncidentLeaderOrReadOnlyCollaborator(BasePermission):
    """Lecture : tout collaborateur accepté. Écriture : leader uniquement."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return IsIncidentCollaborator().has_permission(request, view)
        return IsIncidentLeader().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return IsIncidentCollaborator().has_object_permission(request, view, obj)
        return IsIncidentLeader().has_object_permission(request, view, obj)


class IsSuperAdmin(BasePermission):
    """Autorise uniquement les super admins (is_superuser=True)."""

    message = "Seul un super administrateur peut effectuer cette action."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser

    def has_object_permission(self, request, view, obj):
        return request.user and request.user.is_authenticated and request.user.is_superuser


class IsSuperAdminOrOrgOwnIncident(BasePermission):
    """Super Admin peut supprimer tous les incidents. Organisation ne peut supprimer que ses incidents."""

    message = "Vous n'avez pas la permission de supprimer cet incident."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Super admin peut tout supprimer
        if request.user.is_superuser:
            return True

        # Organisation ne peut supprimer que ses propres incidents
        if isinstance(obj, Incident):
            user_org = request.user.organisation_member
            if user_org:
                # L'incident appartient à l'organisation si:
                # - Il a été reporté par un agent de l'organisation
                # - Ou il a été pris en charge par l'organisation (taken_by)
                if obj.user_id and obj.user_id.organisation_member == user_org:
                    return True
                if obj.taken_by and obj.taken_by.organisation_member == user_org:
                    return True

        return False
