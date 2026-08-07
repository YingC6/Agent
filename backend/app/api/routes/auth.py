"""用户认证路由"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ...api.deps import get_current_user
from ...database import get_db
from ...models.db_models import User
from ...services.security import create_access_token, get_password_hash, verify_password

router = APIRouter(prefix="/auth", tags=["用户认证"])


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=64)
    nickname: str = Field(default="旅行者", max_length=80)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    username: str
    nickname: str
    role: str


class AuthResponse(BaseModel):
    success: bool
    message: str
    token: str | None = None
    user: UserInfo | None = None


def build_auth_response(user: User, message: str) -> AuthResponse:
    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(
        success=True,
        message=message,
        token=token,
        user=UserInfo(id=user.id, username=user.username, nickname=user.nickname, role=user.role)
    )


@router.post("/register", response_model=AuthResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.username == request.username).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")
    user = User(
        username=request.username,
        password_hash=get_password_hash(request.password),
        nickname=request.nickname or request.username
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return build_auth_response(user, "注册成功")


@router.post("/login", response_model=AuthResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    return build_auth_response(user, "登录成功")


@router.get("/me", response_model=UserInfo)
def me(current_user: User = Depends(get_current_user)):
    return UserInfo(id=current_user.id, username=current_user.username, nickname=current_user.nickname, role=current_user.role)
