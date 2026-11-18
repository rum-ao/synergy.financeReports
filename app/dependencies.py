from fastapi import Request, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .auth import read_session_token, COOKIE_NAME


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    data = read_session_token(token)
    if not data:
        return None

    user_id = data.get("uid")
    if not user_id:
        return None

    user = (
        db.query(User)
        .filter(User.id == user_id, User.is_active == True)
        .first()
    )

    return user