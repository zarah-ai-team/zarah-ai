"""auth.py
JWT authentication module for the Travel Itinerary Chatbot API.
Handles user registration, login, token generation, and request authentication.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = logging.getLogger("auth")

# ─── Configuration ───────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "tmc-secret-key-change-in-production-2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24 hours default

# ─── Password hashing (using bcrypt directly for compatibility) ──────────────
import bcrypt as _bcrypt


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

# ─── Bearer token scheme ────────────────────────────────────────────────────
bearer_scheme = HTTPBearer()

# ─── User store (JSON file persistence) ─────────────────────────────────────
USERS: Dict[str, Dict[str, Any]] = {}
USERS_FILE = os.path.join(os.path.dirname(__file__), "data", "users.json")


def _load_users():
    global USERS
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                USERS = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load users: {e}")
            USERS = {}


def _save_users():
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    try:
        with open(USERS_FILE, "w") as f:
            json.dump(USERS, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to save users: {e}")


# Load on import
_load_users()


# ─── Pydantic models ────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: Dict[str, Any]


# ─── Core functions ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _hash_password(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _verify_password(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
        )


def register_user(req: RegisterRequest) -> Dict[str, Any]:
    """Register a new user. Returns user dict (without password)."""
    _load_users()
    if req.username in USERS:
        raise HTTPException(status_code=400, detail="Username already exists")
    # Check email uniqueness
    for u in USERS.values():
        if u.get("email") == req.email:
            raise HTTPException(status_code=400, detail="Email already registered")

    is_admin = req.username == "admin" or len(USERS) == 0
    user = {
        "username": req.username,
        "email": req.email,
        "full_name": req.full_name,
        "hashed_password": hash_password(req.password),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "is_active": True,
        "is_admin": is_admin,
    }
    USERS[req.username] = user
    _save_users()
    # Return without password
    return {k: v for k, v in user.items() if k != "hashed_password"}


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate user by username and password. Returns user dict or None."""
    _load_users()
    user = USERS.get(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return {k: v for k, v in user.items() if k != "hashed_password"}


def login_user(req: LoginRequest) -> TokenResponse:
    """Authenticate and return JWT token."""
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    token = create_access_token(data={"sub": user["username"], "email": user.get("email", "")})
    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


# ─── FastAPI dependency ─────────────────────────────────────────────────────

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> Dict[str, Any]:
    """FastAPI dependency that extracts and validates the JWT Bearer token.
    Returns the decoded payload with user info.
    """
    payload = decode_token(credentials.credentials)
    username = payload.get("sub")
    _load_users()
    user = USERS.get(username)
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="User not found or inactive")
    result = {k: v for k, v in user.items() if k != "hashed_password"}
    if "is_admin" not in result:
        result["is_admin"] = result.get("username") == "admin"
    return result
