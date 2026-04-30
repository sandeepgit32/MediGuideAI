from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from ..database.database import get_db
from ..database.models import User
from ..schemas.user import (
    UserCreate,
    UserResponse,
    Token,
    TokenData,
    PasswordChange,
    HistoryResponse,
    HistoryEntry,
)
from ..utils.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    SECRET_KEY,
    ALGORITHM,
)
from ..services.agent_memory import memory_service

auth_router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(id=user_id)
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == token_data.id).first()
    if user is None:
        raise credentials_exception
    return user


@auth_router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    hashed_password = get_password_hash(user.password)
    new_user = User(email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@auth_router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@auth_router.post("/change-password", response_model=dict)
def change_password(
    passwords: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(passwords.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect old password"
        )

    current_user.hashed_password = get_password_hash(passwords.new_password)
    db.commit()
    return {"message": "Password updated successfully"}


@auth_router.get("/history", response_model=HistoryResponse)
async def get_history(current_user: User = Depends(get_current_user)):
    """Return all Mem0 consultation memories for the authenticated user, newest first.

    Always returns 200.  If the memory service is unavailable or returns no data
    the response will contain an empty ``memories`` list and the frontend will
    show the "No history" state.
    """
    import logging

    _log = logging.getLogger(__name__)
    user_id = str(current_user.id)
    _log.info(
        "GET /auth/history — fetching memories for user_id=%r (email=%r)",
        user_id,
        current_user.email,
    )
    try:
        entries = await memory_service.get_all_memories(user_id)
    except Exception:
        _log.exception(
            "Unexpected error fetching memories for user_id=%r; returning empty list",
            user_id,
        )
        entries = []
    entries.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    _log.info(
        "GET /auth/history — returning %d memories for user_id=%r",
        len(entries),
        user_id,
    )
    return HistoryResponse(
        memories=[
            HistoryEntry(memory=e["memory"], created_at=e["created_at"])
            for e in entries
        ]
    )
