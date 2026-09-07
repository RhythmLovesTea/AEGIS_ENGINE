"""AEGIS-Marine: JWT Authentication, OIDC Claims, and RBAC Security (Architecture 10)."""

from __future__ import annotations

import enum
import logging
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.core.errors import AuthenticationError, AuthorizationError, assert_no_banned_terms

logger = logging.getLogger(__name__)

# HTTP Bearer Security Scheme (auto_error=False allows RFC 7807 handler to format 401)
oauth2_scheme = HTTPBearer(auto_error=False)


class Role(enum.StrEnum):
    """Architecture Section 10: Official RBAC roles."""

    INVESTIGATOR = "investigator"
    ANALYST = "analyst"
    LEGAL_REVIEWER = "legal_reviewer"
    ADMIN = "admin"


# Role to granular permission mapping (Architecture Section 10)
ROLE_PERMISSIONS: dict[str, set[str]] = {
    Role.INVESTIGATOR.value: {
        "cases:create",
        "cases:read",
        "cases:rerun",
        "cases:what_if",
        "dossier:export",
        "dossier:read",
        "replay:read",
    },
    Role.ANALYST.value: {
        "cases:read",
        "cases:what_if",
        "replay:read",
    },
    Role.LEGAL_REVIEWER.value: {
        "cases:read",
        "dossier:read",
        "dossier:export",
        "audit:read",
    },
    Role.ADMIN.value: {
        "cases:create",
        "cases:read",
        "cases:rerun",
        "cases:what_if",
        "dossier:export",
        "dossier:read",
        "replay:read",
        "ahp:config",
        "audit:read",
        "system:admin",
        "users:manage",
    },
}


class CurrentUser(BaseModel):
    """Authenticated user profile with active roles and derived permissions."""

    user_id: str = Field(..., description="Unique user identifier (sub claim)")
    email: str | None = Field(default=None, description="User email address")
    name: str | None = Field(default=None, description="User display name")
    roles: list[str] = Field(default_factory=list, description="Assigned RBAC role names")
    claims: dict[str, Any] = Field(default_factory=dict, description="Raw JWT claims payload")

    @property
    def permissions(self) -> set[str]:
        """Derives flattened set of all active permissions from assigned roles."""
        perms: set[str] = set()
        for r in self.roles:
            role_key = r.lower()
            if role_key in ROLE_PERMISSIONS:
                perms.update(ROLE_PERMISSIONS[role_key])
        return perms

    def has_role(self, role: str | Role) -> bool:
        """Checks whether the user possesses a specific role."""
        role_val = role.value if isinstance(role, Role) else str(role).lower()
        return any(r.lower() == role_val for r in self.roles)

    def has_any_role(self, roles: Sequence[str | Role]) -> bool:
        """Checks whether the user possesses at least one of the specified roles."""
        target_roles = {r.value.lower() if isinstance(r, Role) else str(r).lower() for r in roles}
        user_roles = {r.lower() for r in self.roles}
        return bool(target_roles.intersection(user_roles))

    def has_permission(self, permission: str) -> bool:
        """Checks whether the user possesses a specific granular permission."""
        if self.has_role(Role.ADMIN):
            return True
        return permission in self.permissions


def extract_roles_from_claims(payload: dict[str, Any]) -> list[str]:
    """Extracts user roles from diverse OIDC and standard claim formats.

    Supports:
    - Standard JWT 'roles': ['investigator', ...]
    - Single role string 'role': 'investigator'
    - Keycloak Realm Access: {'realm_access': {'roles': [...]}}
    - Keycloak Resource Access: {'resource_access': {'aegis': {'roles': [...]}}}
    - Custom Auth0 / Clerk namespace: 'https://aegis.marine/roles'
    """
    detected_roles: set[str] = set()

    # 1. Standard root 'roles' list
    if "roles" in payload and isinstance(payload["roles"], list):
        detected_roles.update(str(r).lower() for r in payload["roles"])

    # 2. Single root 'role' string
    if "role" in payload and isinstance(payload["role"], str):
        detected_roles.add(payload["role"].lower())

    # 3. Keycloak realm_access.roles
    realm_access = payload.get("realm_access")
    if (
        isinstance(realm_access, dict)
        and "roles" in realm_access
        and isinstance(realm_access["roles"], list)
    ):
        detected_roles.update(str(r).lower() for r in realm_access["roles"])

    # 4. Keycloak resource_access.<client>.roles
    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        for client_info in resource_access.values():
            if (
                isinstance(client_info, dict)
                and "roles" in client_info
                and isinstance(client_info["roles"], list)
            ):
                detected_roles.update(str(r).lower() for r in client_info["roles"])

    # 5. Namespaced OIDC claims
    for key, val in payload.items():
        if ("roles" in key.lower() or "groups" in key.lower()) and isinstance(val, list):
            detected_roles.update(str(r).lower() for r in val)

    # Filter to known roles
    known_roles = {r.value for r in Role}
    normalized = [r for r in detected_roles if r in known_roles]
    return normalized or list(detected_roles)


def create_access_token(
    subject: str,
    roles: Sequence[str | Role] | None = None,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
    key: str | None = None,
    algorithm: str | None = None,
) -> str:
    """Creates a signed JWT access token for testing or local authentication."""
    now_utc = datetime.now(UTC)
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire_utc = now_utc + delta

    formatted_roles: list[str] = []
    if roles:
        formatted_roles = [r.value if isinstance(r, Role) else str(r).lower() for r in roles]

    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now_utc.timestamp()),
        "exp": int(expire_utc.timestamp()),
        "jti": str(uuid.uuid4()),
        "roles": formatted_roles,
    }

    if extra_claims:
        payload.update(extra_claims)

    secret_key = key or settings.JWT_SECRET_KEY
    alg = algorithm or settings.JWT_ALGORITHM

    token = jwt.encode(payload, secret_key, algorithm=alg)
    return token


def decode_access_token(
    token: str,
    key: str | None = None,
    algorithm: str | None = None,
) -> dict[str, Any]:
    """Decodes and verifies a JWT token. Raises AuthenticationError on failure."""
    secret_key = key or settings.JWT_SECRET_KEY
    alg = algorithm or settings.JWT_ALGORITHM

    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[alg],
            options={"verify_exp": True, "verify_signature": True},
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        logger.warning("Rejected expired JWT token: %s", e)
        raise AuthenticationError("Token has expired.") from e
    except jwt.InvalidTokenError as e:
        logger.warning("Rejected invalid JWT token: %s", e)
        raise AuthenticationError("Invalid token signature or payload.") from e


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
) -> CurrentUser:
    """FastAPI dependency extracting and verifying the authenticated user."""
    if not credentials or not credentials.credentials:
        raise AuthenticationError("Authentication credentials were not provided.")

    token = credentials.credentials
    payload = decode_access_token(token)

    subject = payload.get("sub")
    if not subject:
        raise AuthenticationError("Token missing required 'sub' subject claim.")

    roles = extract_roles_from_claims(payload)
    email = payload.get("email")
    name = payload.get("name") or payload.get("preferred_username")

    return CurrentUser(
        user_id=str(subject),
        email=str(email) if email else None,
        name=str(name) if name else None,
        roles=roles,
        claims=payload,
    )


def require_roles(
    allowed_roles: Sequence[str | Role],
) -> Callable[[CurrentUser], CurrentUser]:
    """FastAPI dependency factory enforcing RBAC role membership.

    Admins are always granted access. If the user lacks the required roles,
    an RFC 7807 403 Forbidden problem detail is raised.
    """
    normalized_allowed = {
        r.value.lower() if isinstance(r, Role) else str(r).lower() for r in allowed_roles
    }

    def role_checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        # Admin override
        if current_user.has_role(Role.ADMIN):
            return current_user

        if current_user.has_any_role(list(normalized_allowed)):
            return current_user

        allowed_str = ", ".join(sorted(normalized_allowed))
        detail_msg = f"Insufficient permissions. Required one of roles: [{allowed_str}]."
        assert_no_banned_terms(detail_msg, context_label="Role Denial")
        raise AuthorizationError(detail_msg)

    return role_checker


def require_permissions(
    required_permissions: Sequence[str],
) -> Callable[[CurrentUser], CurrentUser]:
    """FastAPI dependency factory enforcing granular permission requirements."""
    target_permissions = set(required_permissions)

    def permission_checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.has_role(Role.ADMIN):
            return current_user

        missing = target_permissions - current_user.permissions
        if not missing:
            return current_user

        missing_str = ", ".join(sorted(missing))
        detail_msg = f"Insufficient permissions. Missing required permissions: [{missing_str}]."
        assert_no_banned_terms(detail_msg, context_label="Permission Denial")
        raise AuthorizationError(detail_msg)

    return permission_checker
