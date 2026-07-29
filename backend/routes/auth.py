from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import ConsultationHistory, User
from ..schemas.user import (
    HistoryEntry,
    HistoryResponse,
    PasswordChange,
    Token,
    TokenData,
    UserCreate,
    UserResponse,
)
from ..utils.security import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_password_hash,
    verify_password,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# OAuth2PasswordBearer is related to the OAuth 2.0 standard, but this application
# uses it in a simplified way with username/password authentication and JWT tokens.
# The tokenUrl parameter does not implement the login endpoint or perform authentication.
# It simply tells FastAPI and the generated Swagger documentation where clients should
# send their username and password to obtain an access token.
# When you open Swagger UI (/docs), FastAPI uses tokenUrl to power the Authorize button:
# 1. You click Authorize.
# 2. Swagger sends your username and password to /auth/login.
# 3. It receives the access token.
# 4. Swagger automatically includes it in future requests as:

# `oauth2_scheme` an object that knows how to extract a Bearer token from an incoming request.
# The interesting part happens when FastAPI executes it as a dependency:


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    """
    Authenticate the current user using a JWT Bearer token.

    The function extracts the JWT from the Authorization header using
    OAuth2PasswordBearer, verifies the token's signature and expiration,
    retrieves the user ID from the 'sub' (subject) claim, and fetches the
    corresponding user from the database. If the token is invalid, or the
    user does not exist, it raises a 401 Unauthorized exception.

    `token: str = Depends(oauth2_scheme)` extracts the Bearer token using
    `oauth2_scheme` from the request header and the extracted JWT is passed
    into the `token` parameter.

    Depends() tells FastAPI: "Before calling this function, first execute
    another function (or class) and pass its result as this parameter."

    Returns:
        User: The authenticated user object.
    """
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
# The `status_code` is explicitly specified here. If you don't specify status_code,
# FastAPI returns: 200 OK.
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
    # commit() saves the data, while refresh() synchronizes the Python object
    # with the latest state in the database. After committing, SQLAlchemy needs
    # to know which specific object should be reloaded from the database.
    # Therefore, we call db.refresh(new_user) instead of db.refresh()
    db.refresh(new_user)
    return new_user


@auth_router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    # form_data: OAuth2PasswordRequestForm = Depends() This is a built-in FastAPI
    # dependency that extracts the username and password from an login request.
    # A database session is injected using Depends(get_db) to verify the user's credentials.
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": str(user.id)})
    # A Bearer token is an access token that a client includes in the HTTP Authorization
    # header to prove it is authenticated.
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
    # db.refresh() is mainly used after creating a new record because the database
    # may generate values such as the primary key (id), timestamps, or default column
    # values. After an update, the SQLAlchemy object already contains the new values
    # because we modified the object directly before calling db.commit().
    return {"message": "Password updated successfully"}


@auth_router.get("/history", response_model=HistoryResponse)
def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all consultation history for the authenticated user, newest first.

    Queries the ``consultation_history`` MySQL table. The ``memory`` field
    combines severity and recommended action so the frontend card displays a
    meaningful one-line summary. ``created_at`` is an ISO 8601 string so the
    frontend ``groupByDate()`` helper can parse it reliably.
    """
    import logging

    _log = logging.getLogger(__name__)
    user_id = str(current_user.id)
    _log.info("GET /auth/history for user_id=%r", user_id)

    rows = (
        db.query(ConsultationHistory)
        .filter(ConsultationHistory.user_id == user_id)
        .order_by(ConsultationHistory.created_at.desc())
        .all()
    )
    _log.info("Returning %d history entries for user_id=%r", len(rows), user_id)
    return HistoryResponse(
        memories=[
            HistoryEntry(
                memory=f"{row.severity.upper()} — {row.recommended_action} (symptoms: {row.symptoms})",
                created_at=row.created_at.isoformat(),
                summary=row.summary,
            )
            for row in rows
        ]
    )
