"""Canonical web-role logic for the dashboard's 3 roles.

Single source of truth shared by the API serializers (what the frontend reads)
and the DRF permission classes (what the backend enforces). See
Dashboardv2/Map_Action_Logique_des_roles.md.

Web roles (dashboard): super_admin, org_admin, bureau_agent.
field_agent is mobile-only and has no dashboard access.
"""

SUPER_ADMIN = "super_admin"
ORG_ADMIN = "org_admin"
BUREAU_AGENT = "bureau_agent"
FIELD_AGENT = "field_agent"

# Roles allowed to use the web dashboard at all.
WEB_ROLES = (SUPER_ADMIN, ORG_ADMIN, BUREAU_AGENT)


def get_web_role(user):
    """Return the canonical web role for a user, or None.

    is_superuser wins (super admin is a platform role, not an org role — D3).
    Otherwise the user's org_role drives it.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "is_superuser", False):
        return SUPER_ADMIN
    return getattr(user, "org_role", None) or None


def is_super_admin(user):
    return get_web_role(user) == SUPER_ADMIN


def is_org_admin(user):
    return get_web_role(user) == ORG_ADMIN


def is_bureau_agent(user):
    return get_web_role(user) == BUREAU_AGENT


def has_web_access(user):
    return get_web_role(user) in WEB_ROLES
