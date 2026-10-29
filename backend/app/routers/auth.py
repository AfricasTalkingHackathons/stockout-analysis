from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db, utcnow
from app.deps import get_current_user, get_token_payload
from app.models import RevokedToken, User
from app.ratelimit import client_ip, sensitive_limit
from app.schemas import LoginIn, TokenOut, UserOut
from app.security import create_access_token, verify_password
from app.serializers import user_dict
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut, dependencies=[Depends(sensitive_limit("login"))])
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        audit(db, "auth.login_failed", "user", user.id if user else None, actor_label=body.email.lower(),
              ip=client_ip(request))
        db.commit()
        raise HTTPException(401, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(403, "This account is disabled")
    token, _, expires_in = create_access_token(user.id)
    user.last_login_at = utcnow()
    audit(db, "auth.login", "user", user.id, actor=user, ip=client_ip(request))
    db.commit()
    return {"access_token": token, "expires_in": expires_in, "user": user_dict(user)}


@router.post("/logout", status_code=204)
def logout(payload: dict = Depends(get_token_payload), user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    db.merge(RevokedToken(jti=payload["jti"], expires_at=exp))
    db.query(RevokedToken).filter(RevokedToken.expires_at < utcnow() - timedelta(minutes=1)).delete()
    audit(db, "auth.logout", "user", user.id, actor=user)
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user_dict(user)
