from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select
from passlib.context import CryptContext
from app.database import engine
from app.models import User
from app.auth.jwt_handler import create_access_token  # ✅ import correcto
from pydantic import BaseModel
from traceback import print_exc

router = APIRouter(prefix="/auth", tags=["Auth"])

# Contexto de contraseñas con bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ✅ Funciones auxiliares
def get_password_hash(password: str):
    # Aseguramos que password es str y no bytes
    if isinstance(password, bytes):
        password = password.decode("utf-8")

    # bcrypt no admite más de 72 bytes → truncamos por seguridad
    password = password[:72]

    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña coincide con su hash."""
    try:
        return pwd_context.verify(plain_password[:72], hashed_password)
    except Exception:
        return False


# ✅ Endpoint de registro (query params o Swagger UI)
@router.post("/register")
def register_user(email: str, password: str, role: str = "tecnico"):
    print(f"ENTRAMOS EN REGISTER | email={email}, role={role}")

    try:
        with Session(engine) as session:
            existing = session.exec(select(User).where(User.email == email)).first()
            if existing:
                raise HTTPException(status_code=400, detail="Usuario ya existe")

            hashed = get_password_hash(password)
            new_user = User(email=email, password_hash=hashed, role=role)
            session.add(new_user)
            session.commit()
            session.refresh(new_user)

            return {"id": new_user.id, "email": new_user.email, "role": new_user.role}

    except Exception as e:
        print("ERROR REGISTRO USUARIO")
        print_exc()
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


# ✅ Modelo de login
class UserLogin(BaseModel):
    email: str
    password: str


# ✅ Endpoint de login
@router.post("/login")
def login(user: UserLogin):
    with Session(engine) as session:
        db_user = session.exec(select(User).where(User.email == user.email)).first()

        if not db_user or not verify_password(user.password, db_user.password_hash):
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        token = create_access_token({"sub": db_user.email, "role": db_user.role})
        return {"access_token": token, "token_type": "bearer"}

