from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.models import User
from app.schemas.schemas import RegisterIn, Token, UserOut
from app.core.security import hash_password, verify_password, create_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=Token)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already registered")
    role_map = {"balcony": "balcony", "buyer": "buyer"}
    role = role_map.get(data.mode, "farmer")
    user = User(name=data.name, email=data.email,
                hashed_password=hash_password(data.password),
                role=role, mode=data.mode, language=data.language,
                state=data.state, district=data.district)
    db.add(user); db.commit(); db.refresh(user)
    return Token(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 form uses 'username' field — we treat it as email
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password")
    return Token(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
