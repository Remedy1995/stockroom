import hashlib
import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import delete
from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.db import get_db
from app.models import Session, User, now

password_hasher = PasswordHash.recommended()
DUMMY_HASH = password_hasher.hash('constant-time-dummy-password')
bearer = HTTPBearer(auto_error=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(plain, hashed):
    return password_hasher.verify(plain, hashed)


def issue_session(db, user, response):
    token = secrets.token_urlsafe(48)
    settings = get_settings()
    db.execute(delete(Session).where(Session.expires_at <= now()))
    db.add(Session(token_hash=digest(token), user_id=user.id, expires_at=now() + settings.session_hours * 3600))
    response.set_cookie('stockroom_session', token, httponly=True, secure=settings.secure_cookies,
                        samesite='strict', max_age=settings.session_hours * 3600, path='/')
    return token


def current_user(request: Request, credential: HTTPAuthorizationCredentials | None = Depends(bearer), db: DBSession = Depends(get_db)):
    token = credential.credentials if credential else request.cookies.get('stockroom_session')
    session = db.get(Session, digest(token)) if token else None
    if not session or session.expires_at <= now():
        raise HTTPException(401, 'Sign in to continue.', headers={'WWW-Authenticate': 'Bearer'})
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, 'Session is no longer valid.')
    request.state.session_hash = session.token_hash
    return user


def editor(user: User = Depends(current_user)):
    if user.role not in {'owner', 'editor'}:
        raise HTTPException(403, 'Your role has read-only access.')
    return user


def owner(user: User = Depends(current_user)):
    if user.role != 'owner':
        raise HTTPException(403, 'Only the workspace owner can manage the team.')
    return user
