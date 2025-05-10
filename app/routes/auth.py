from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from jose import JWTError, jwt
from app.security.jwt_handler import get_password_hash, verify_password, create_access_token, SECRET_KEY, ALGORITHM
import asyncpg
from datetime import timedelta

auth_router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

async def get_db():
    return await asyncpg.connect(
        user="kong", 
        password="kong", 
        database="kong", 
        host="db"
    )

# Registro de usuarios
@auth_router.post("/signup")
async def signup(user: UserCreate):
    db = await get_db()
    hashed_password = get_password_hash(user.password)

    try:
        await db.execute(
            "INSERT INTO users (username, email, password_hash) VALUES ($1, $2, $3)",
            user.username, user.email, hashed_password
        )
        await db.close()
        return {"message": "Usuario registrado exitosamente", "username": user.username}
    except asyncpg.UniqueViolationError:
        await db.close()
        raise HTTPException(status_code=400, detail="El usuario o email ya existen.")

# Login y generación de token
@auth_router.post("/token")
async def login(user: UserLogin):
    db = await get_db()
    result = await db.fetchrow("SELECT * FROM users WHERE username=$1", user.username)

    if result is None or not verify_password(user.password, result["password_hash"]):
        await db.close()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=30))

    await db.close()
    return {"access_token": access_token, "token_type": "bearer"}

# Ruta protegida
@auth_router.get("/protected-route")
async def protected_route(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        return {"message": f"Bienvenido, {username}. Esta es una ruta protegida."}
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")