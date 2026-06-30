"""Organisations actives sur un incident.

Couche service partagée par les serializers incident (liste + détail) pour
exposer, de façon explicite et cohérente : l'organisation qui a pris l'incident
en charge, et la liste de toutes les organisations qui agissent dessus. Conçu
pour s'appuyer sur des relations préchargées (select_related / prefetch_related)
afin d'éviter le N+1 en liste.
"""
from django.db.models import Q

from ..models import ORG_ASSIGNMENT_ACCEPTED, COLLAB_STATUS_ACCEPTED


def org_acting_q(user):
    """Filtre Q : incidents sur lesquels l'utilisateur (ou son organisation) agit
    réellement — a pris en charge (perso/org), org assignée acceptée, collaboration
    acceptée de son org, ou agent assigné. Source unique partagée par
    /my-interventions/ et le scope ``mine`` de /incident-filter/."""
    q = Q(taken_by=user) | Q(assignments__agent=user)
    org = getattr(user, 'organisation_member', None)
    if org:
        q |= Q(taken_by__organisation_member=org)
        q |= Q(org_assignments__organisation=org,
               org_assignments__status=ORG_ASSIGNMENT_ACCEPTED)
        q |= Q(collaboration__user__organisation_member=org,
               collaboration__status=COLLAB_STATUS_ACCEPTED)
    return q

RELATION_LEADER = 'leader'        # a pris l'incident en charge (taken_by)
RELATION_ASSIGNED = 'assigned'    # assignée par le Super Admin et a accepté
RELATION_COLLABORATOR = 'collaborator'  # collabore (Collaboration acceptée)

_RANK = {RELATION_LEADER: 0, RELATION_ASSIGNED: 1, RELATION_COLLABORATOR: 2}


def taken_by_organisation(incident):
    """{'id', 'name'} de l'organisation qui a pris l'incident en charge, ou None."""
    taken_by = getattr(incident, 'taken_by', None)
    org = getattr(taken_by, 'organisation_member', None) if taken_by else None
    return {'id': org.id, 'name': org.name} if org else None


def acting_organisations(incident):
    """Liste dédupliquée des organisations actives sur l'incident.

    Chaque entrée : {'id', 'name', 'relation'} où relation ∈
    {leader, assigned, collaborator}. Si une organisation cumule plusieurs
    relations on garde la plus forte (leader > assigned > collaborator).
    """
    found = {}

    def add(org, relation):
        if not org:
            return
        existing = found.get(org.id)
        if existing is None or _RANK[relation] < _RANK[existing['relation']]:
            found[org.id] = {'id': org.id, 'name': org.name, 'relation': relation}

    # 1. l'organisation qui a pris en charge (leader)
    taken_by = getattr(incident, 'taken_by', None)
    if taken_by:
        add(getattr(taken_by, 'organisation_member', None), RELATION_LEADER)

    # 2. assignations org acceptées
    for assignment in incident.org_assignments.all():
        if assignment.status == ORG_ASSIGNMENT_ACCEPTED:
            add(assignment.organisation, RELATION_ASSIGNED)

    # 3. collaborations acceptées (org du collaborateur)
    for collab in incident.collaboration_set.all():
        if collab.status == COLLAB_STATUS_ACCEPTED:
            add(getattr(collab.user, 'organisation_member', None), RELATION_COLLABORATOR)

    return list(found.values())
