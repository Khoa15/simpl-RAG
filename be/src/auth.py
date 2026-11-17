"""JWT bearer authentication. The user id comes only from the signed token's `sub` claim."""
import re
import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import Settings, get_settings

_USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_bearer = HTTPBearer(auto_error=False)


def issue_token(user_id: str, settings: Settings) -> str:
    if not _USER_ID.match(user_id):
        raise ValueError("user_id must be 1-64 characters of letters, digits, '_' or '-'")
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + settings.jwt_ttl_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError:
        raise unauthorized
    user_id = payload.get("sub", "")
    if not isinstance(user_id, str) or not _USER_ID.match(user_id):
        raise unauthorized
    return user_id


def main() -> None:
    """Issue a token: python -m src.auth <user_id>"""
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m src.auth <user_id>")
    print(issue_token(sys.argv[1], get_settings()))


if __name__ == "__main__":
    main()
