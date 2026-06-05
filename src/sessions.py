from fastapi import HTTPException, Request

from .security import new_csrf_token

SESSION_USER_KEY = "username"


def get_session_username(request: Request) -> str | None:
    username = request.session.get(SESSION_USER_KEY)
    if isinstance(username, str) and username:
        return username
    return None


def require_session_username(request: Request) -> str:
    username = get_session_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return username


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not isinstance(token, str) or not token:
        token = new_csrf_token()
        request.session["csrf_token"] = token
    return token


def verify_form_csrf(request: Request, submitted: str | None) -> None:
    import secrets

    expected = request.session.get("csrf_token")
    if not expected or not submitted:
        raise HTTPException(status_code=403, detail="CSRF validation failed.")
    if not secrets.compare_digest(str(expected), str(submitted)):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def login_user(request: Request, username: str) -> None:
    # Rotate session id on privilege change (mitigate session fixation).
    csrf = request.session.get("csrf_token")
    request.session.clear()
    if csrf:
        request.session["csrf_token"] = csrf
    request.session[SESSION_USER_KEY] = username


def logout_user(request: Request) -> None:
    request.session.clear()
