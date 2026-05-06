"""Permissions custom liées à la collaboration sur un incident.

Ces permissions s'appuient sur le modèle suivant :
  - `Incident.taken_by` désigne le leader (User / organisation) ;
  - `Collaboration(user, incident, role)` matérialise la relation entre
    une organisation et un incident, avec un rôle (leader/contributor/observer)
    et un `status` (pending/accepted/declined).

Rappel : dans ce projet, une "organisation" est un `User` avec `user_type='elu'`.
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
    """Autorise uniquement le leader de l'incident (Incident.taken_by)."""

    message = "Seul le leader de l'incident peut effectuer cette action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        incident = _get_incident_from_view(view, request)
        if incident is None:
            # si pas d'incident dans l'URL, on délègue à has_object_permission
            return True
        return incident.taken_by_id == request.user.id

    def has_object_permission(self, request, view, obj):
        incident = getattr(obj, 'incident', obj if isinstance(obj, Incident) else None)
        if incident is None:
            return False
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
