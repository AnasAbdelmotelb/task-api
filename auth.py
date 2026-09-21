import os

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client, Client
from supabase_auth.types import User


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.getenv("ADMIN_EMAILS", "").split(",")
    if email.strip()
}

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> User:
    """Reusable auth guard: verifies the bearer token with Supabase.

    Apply as a dependency to any route that should only answer for a
    logged-in user; the route only runs once this returns.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail={"error": "Access token required"}
        )

    try:
        response = supabase.auth.get_user(credentials.credentials)
    except Exception:
        response = None

    if response is None or response.user is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid or expired token"}
        )

    return response.user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Same guard as get_current_user, plus an authorization check.

    401 ("I don't know you") is handled by get_current_user above.
    403 ("I know you, and no.") is the authorization check here.
    """
    if user.email is None or user.email.lower() not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=403,
            detail={"error": "Admin access required"}
        )

    return user
