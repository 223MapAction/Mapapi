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
from .roles import (
    is_super_admin,
    is_org_admin,
    is_bureau_agent,
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


def _is_internal_org_member(incident, user):
    """En prise en charge INTERNE, tout membre de l'organisation propriétaire
    (celle de ``incident.taken_by``) est considéré comme collaborateur de
    l'incident, au même titre que le leader.

    Aligne les permissions sur le comportement déjà implémenté côté discussion
    (``DiscussionMessageView``), où les membres de l'org propriétaire participent
    à l'incident interne de leur organisation. Sans cela, un agent de bureau (ou
    l'admin) ne pouvait pas voir les tâches / sous-ressources d'un incident pris
    en charge en interne par SON org (403/404), alors qu'il y a accès au chat.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if not incident or getattr(incident, 'take_in_charge_mode', None) != 'internal':
        return False
    owner = getattr(incident, 'taken_by', None)
    owner_org = getattr(owner, 'organisation_member_id', None)
    user_org = getattr(user, 'organisation_member_id', None)
    return bool(owner_org and user_org and owner_org == user_org)


class IsIncidentLeader(BasePermission):
    """Autorise uniquement le leader de l'incident.
    Le leader est déterminé par une Collaboration acceptée de rôle 'leader',
    ou par défaut le premier utilisateur qui a pris en charge l'incident (taken_by).
    """

    message = "Seul le leader de l'incident peut effectuer cette action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Le super admin (plateforme) a un accès complet aux collaborations,
        # tâches et discussions de tout incident, sans être leader/contributeur.
        if is_super_admin(request.user):
            return True
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
        if is_super_admin(request.user):
            return True
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
        # Le super admin (plateforme) a un accès complet aux collaborations,
        # tâches et discussions de tout incident, sans être leader/contributeur.
        if is_super_admin(request.user):
            return True
        incident = _get_incident_from_view(view, request)
        if incident is None:
            return True
        if incident.taken_by_id == request.user.id:
            return True
        if _is_internal_org_member(incident, request.user):
            return True
        return Collaboration.objects.filter(
            incident=incident, user=request.user, status='accepted'
        ).exists()

    def has_object_permission(self, request, view, obj):
        if is_super_admin(request.user):
            return True
        incident = getattr(obj, 'incident', obj if isinstance(obj, Incident) else None)
        if incident is None:
            return False
        if incident.taken_by_id == request.user.id:
            return True
        if _is_internal_org_member(incident, request.user):
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
        # Le super admin (plateforme) a un accès complet aux collaborations,
        # tâches et discussions de tout incident, sans être leader/contributeur.
        if is_super_admin(request.user):
            return True
        # Les méthodes de lecture restent autorisées pour tous les collaborateurs
        if request.method in SAFE_METHODS:
            return IsIncidentCollaborator().has_permission(request, view)
        incident = _get_incident_from_view(view, request)
        if incident is None:
            return True
        if _is_internal_org_member(incident, request.user):
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
        # Le super admin (plateforme) a un accès complet aux collaborations,
        # tâches et discussions de tout incident, sans être leader/contributeur.
        if is_super_admin(request.user):
            return True
        if request.method in SAFE_METHODS:
            return IsIncidentCollaborator().has_permission(request, view)
        incident = _get_incident_from_view(view, request)
        if incident is None:
            return True
        if incident.taken_by_id == request.user.id:
            return True
        if _is_internal_org_member(incident, request.user):
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


class IsSuperAdminRole(BasePermission):
    """Autorise uniquement le rôle web super_admin (cf. roles.py)."""

    message = "Seul un super administrateur peut effectuer cette action."

    def has_permission(self, request, view):
        return is_super_admin(request.user)

    def has_object_permission(self, request, view, obj):
        return is_super_admin(request.user)


class IsOrgAdmin(BasePermission):
    """Autorise uniquement le rôle web org_admin (Admin d'organisation)."""

    message = "Seul un administrateur d'organisation peut effectuer cette action."

    def has_permission(self, request, view):
        return is_org_admin(request.user)

    def has_object_permission(self, request, view, obj):
        return is_org_admin(request.user)


class IsAgentBureau(BasePermission):
    """Autorise uniquement le rôle web bureau_agent (Agent de bureau)."""

    message = "Seul un agent de bureau peut effectuer cette action."

    def has_permission(self, request, view):
        return is_bureau_agent(request.user)

    def has_object_permission(self, request, view, obj):
        return is_bureau_agent(request.user)


class IsOrgOperative(BasePermission):
    """Autorise un membre opérationnel d'une organisation (org_admin OU bureau_agent)."""

    message = "Cette action est réservée aux membres d'une organisation."

    def has_permission(self, request, view):
        return is_org_admin(request.user) or is_bureau_agent(request.user)

    def has_object_permission(self, request, view, obj):
        return is_org_admin(request.user) or is_bureau_agent(request.user)


class IsSuperAdminOrOrgOwnIncident(BasePermission):
    """Suppression d'incident réservée au Super Admin (spec §6 : Corbeille = Super Admin only).

    Conservée pour compat (delete path), mais ne laisse plus les organisations
    supprimer leurs propres incidents.
    """

    message = "Seul un super administrateur peut supprimer un incident."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Suppression d'incident : Super Admin uniquement.
        return is_super_admin(request.user)
