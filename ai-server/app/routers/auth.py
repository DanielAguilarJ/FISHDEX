import uuid
import logging
import hashlib
import os
import base64
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel

from app.database import get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ─── Auth helper schemas ────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str = "fisherman"

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str

class LoginResponse(BaseModel):
    token: str
    user: UserResponse

# ─── Security helpers ───────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + key.hex()

def verify_password(password: str, hashed: str) -> bool:
    try:
        salt_hex, key_hex = hashed.split(":")
        salt = bytes.fromhex(salt_hex)
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return key.hex() == key_hex
    except Exception:
        return False

def generate_token(user_id: str) -> str:
    # A simple token is a base64 encoded user_id
    return base64.b64encode(user_id.encode('utf-8')).decode('utf-8')

def get_user_id_from_token(token: str) -> str:
    try:
        return base64.b64decode(token.encode('utf-8')).decode('utf-8')
    except Exception:
        return ""

def get_current_user_id(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ")[1]
    user_id = get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_id

# ─── Endpoints ─────────────────────────────────────────────────────────
@router.post("/register", response_model=UserResponse)
def register(req: RegisterRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if user already exists
    cursor.execute("SELECT id FROM users WHERE email = ?", (req.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="El correo ya está registrado")
        
    user_id = str(uuid.uuid4())
    pw_hash = hash_password(req.password)
    now = datetime.now(timezone.utc).isoformat()
    
    try:
        # Create user
        cursor.execute(
            "INSERT INTO users (id, email, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, req.email, pw_hash, req.name, req.role, now)
        )
        
        # Create initial user stats
        cursor.execute(
            "INSERT INTO user_stats (id, user_id, total_xp, total_sightings, total_species, updated_at) VALUES (?, ?, 0, 0, 0, ?)",
            (str(uuid.uuid4()), user_id, now)
        )
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Failed to register user: {e}")
        raise HTTPException(status_code=500, detail="Error interno al registrar usuario")
        
    conn.close()
    return UserResponse(id=user_id, email=req.email, name=req.name, role=req.role)

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, email, password_hash, name, role FROM users WHERE email = ?", (req.email,))
    row = cursor.fetchone()
    conn.close()
    
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
        
    user_id = row["id"]
    token = generate_token(user_id)
    
    return LoginResponse(
        token=token,
        user=UserResponse(
            id=user_id,
            email=row["email"],
            name=row["name"],
            role=row["role"]
        )
    )

@router.get("/me", response_model=UserResponse)
def get_me(user_id: str = Depends(get_current_user_id)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, email, name, role FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
    return UserResponse(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        role=row["role"]
    )
