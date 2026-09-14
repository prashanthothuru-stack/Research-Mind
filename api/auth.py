from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.db.store import Store
from app.deps import get_store
from app.security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthIn(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)


@router.post("/register")
def register(body: AuthIn, store: Annotated[Store, Depends(get_store)], settings: Annotated[Settings, Depends(get_settings)]):
    if store.get_user_by_email(body.email):
        raise HTTPException(400, "Email already registered")
    user = store.create_user(body.email, hash_password(body.password))
    token = create_token(user["id"], user["email"], settings)
    return {"token": token, "user": user}


@router.post("/login")
def login(body: AuthIn, store: Annotated[Store, Depends(get_store)], settings: Annotated[Settings, Depends(get_settings)]):
    user = store.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user["id"], user["email"], settings)
    return {"token": token, "user": {"id": user["id"], "email": user["email"]}}
