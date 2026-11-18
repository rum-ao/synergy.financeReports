import os

from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

SECRET_KEY = os.getenv("SECRET_KEY", "FbE58BDhMNB_AmX_Nt")

COOKIE_NAME = "finance_session"
SESSION_MAX_AGE = 60 * 60 * 8  # 8 часов

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(SECRET_KEY)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"uid": user_id}, salt="session")


def read_session_token(token: str) -> dict | None:
    try:
        return serializer.loads(token, salt="session", max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None