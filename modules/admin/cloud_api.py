"""Cloud API endpoints for collection management."""

import logging
import bcrypt
import jwt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# JWT secret key (in production, load from environment)
JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 30

# In-memory storage for collections (in production, use database)
# Format: collection_id -> collection_data
COLLECTIONS = {}
# Format: alias -> collection_id
ALIASES = {}


# Request/Response Models

class CreateCollectionRequest(BaseModel):
    name: str
    presenter_name: str = ""
    description: str = ""
    is_private: bool = False
    max_slides: int = 100
    admin_username: str
    admin_password_hash: str


class CreateCollectionResponse(BaseModel):
    session_id: str
    success: bool = True


class VerifyPasswordRequest(BaseModel):
    password: str


class VerifyPasswordResponse(BaseModel):
    verified: bool
    session_id: Optional[str] = None
    owner_username: Optional[str] = None
    name: Optional[str] = None
    session_token: Optional[str] = None


class UpdateAliasRequest(BaseModel):
    alias: Optional[str]


class UpdateAliasResponse(BaseModel):
    success: bool
    session_id: str
    alias: Optional[str]
    message: Optional[str] = None


class UpdatePasswordRequest(BaseModel):
    admin_username: str
    new_password_hash: str


class UpdatePasswordResponse(BaseModel):
    success: bool
    message: str


class CollectionInfo(BaseModel):
    session_id: str
    name: str
    description: str
    presenter_name: str
    created_at: str
    is_private: bool
    has_password: bool
    alias: Optional[str] = None


class StartTalkRequest(BaseModel):
    title: str
    description: str = ""


class StartTalkResponse(BaseModel):
    success: bool
    talk: Dict[str, Any]


# Helper Functions

def generate_collection_id() -> str:
    """Generate a random collection ID like AUA-6538."""
    import random
    import string

    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=4))
    return f"{letters}-{numbers}"


def generate_session_token(collection_id: str, username: str, device_fingerprint: str = None) -> str:
    """Generate JWT session token.

    Args:
        collection_id: Collection ID
        username: Owner username
        device_fingerprint: Optional device fingerprint

    Returns:
        JWT token string
    """
    payload = {
        "sub": collection_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": datetime.utcnow(),
    }

    if device_fingerprint:
        payload["device_fingerprint"] = device_fingerprint

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode session token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload or None if invalid
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash.

    Args:
        plain_password: Plain text password
        hashed_password: Bcrypt hash

    Returns:
        True if password matches
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


# API Router

router = APIRouter(prefix="/api/cloud", tags=["cloud"])


@router.post("/session/create", response_model=CreateCollectionResponse)
async def create_collection(request: CreateCollectionRequest):
    """Create a new collection with owner credentials.

    Args:
        request: Collection creation request

    Returns:
        Collection ID

    Raises:
        HTTPException: If creation fails
    """
    try:
        # Generate collection ID
        collection_id = generate_collection_id()

        # Ensure uniqueness
        while collection_id in COLLECTIONS:
            collection_id = generate_collection_id()

        # Create collection
        collection = {
            "session_id": collection_id,
            "name": request.name,
            "description": request.description,
            "presenter_name": request.presenter_name,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "is_private": request.is_private,
            "has_password": bool(request.admin_password_hash),
            "alias": None,
            "owner_username": request.admin_username,
            "admin_password_hash": request.admin_password_hash,
            "max_slides": request.max_slides,
            "talks": []
        }

        # Store collection
        COLLECTIONS[collection_id] = collection

        logger.info(f"Created collection: {collection_id} for {request.admin_username}")

        return CreateCollectionResponse(
            session_id=collection_id,
            success=True
        )

    except Exception as e:
        logger.error(f"Failed to create collection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/{id_or_alias}/verify", response_model=VerifyPasswordResponse)
async def verify_collection_password(id_or_alias: str, request: VerifyPasswordRequest):
    """Verify collection password and grant access.

    Args:
        id_or_alias: Collection ID or alias
        request: Password verification request

    Returns:
        Verification result with session token if successful

    Raises:
        HTTPException: If collection not found or password invalid
    """
    try:
        # Find collection by ID or alias
        collection_id = id_or_alias

        if id_or_alias in ALIASES:
            collection_id = ALIASES[id_or_alias]

        if collection_id not in COLLECTIONS:
            raise HTTPException(status_code=404, detail="Collection not found")

        collection = COLLECTIONS[collection_id]

        # Check if collection has password
        if not collection.get("admin_password_hash"):
            raise HTTPException(status_code=400, detail="Collection has no password set")

        # Verify password
        if not verify_password(request.password, collection["admin_password_hash"]):
            logger.warning(f"Invalid password attempt for collection: {collection_id}")
            return VerifyPasswordResponse(verified=False)

        # Generate session token
        session_token = generate_session_token(
            collection_id,
            collection["owner_username"]
        )

        logger.info(f"Password verified for collection: {collection_id}")

        return VerifyPasswordResponse(
            verified=True,
            session_id=collection_id,
            owner_username=collection["owner_username"],
            name=collection["name"],
            session_token=session_token
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to verify password: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{id_or_alias}", response_model=CollectionInfo)
async def get_collection_info(id_or_alias: str):
    """Get collection information.

    Args:
        id_or_alias: Collection ID or alias

    Returns:
        Collection metadata

    Raises:
        HTTPException: If collection not found
    """
    try:
        # Find collection by ID or alias
        collection_id = id_or_alias

        if id_or_alias in ALIASES:
            collection_id = ALIASES[id_or_alias]

        if collection_id not in COLLECTIONS:
            raise HTTPException(status_code=404, detail="Collection not found")

        collection = COLLECTIONS[collection_id]

        # Return public information only (no password hash)
        return CollectionInfo(
            session_id=collection_id,
            name=collection["name"],
            description=collection["description"],
            presenter_name=collection["presenter_name"],
            created_at=collection["created_at"],
            is_private=collection["is_private"],
            has_password=collection["has_password"],
            alias=collection.get("alias")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/{session_id}/alias", response_model=UpdateAliasResponse)
async def update_collection_alias(session_id: str, request: UpdateAliasRequest):
    """Update collection alias.

    Args:
        session_id: Collection ID (not alias)
        request: Alias update request

    Returns:
        Update result

    Raises:
        HTTPException: If collection not found or alias already in use
    """
    try:
        if session_id not in COLLECTIONS:
            raise HTTPException(status_code=404, detail="Collection not found")

        collection = COLLECTIONS[session_id]
        old_alias = collection.get("alias")
        new_alias = request.alias

        # Remove old alias mapping
        if old_alias and old_alias in ALIASES:
            del ALIASES[old_alias]

        # Validate new alias
        if new_alias:
            # Check if already in use
            if new_alias in ALIASES:
                raise HTTPException(
                    status_code=409,
                    detail=f"Alias '{new_alias}' already in use"
                )

            # Validate format (alphanumeric, hyphens, underscores)
            if not new_alias.replace('-', '').replace('_', '').isalnum():
                raise HTTPException(
                    status_code=400,
                    detail="Alias can only contain letters, numbers, hyphens, and underscores"
                )

            # Validate length
            if len(new_alias) < 3 or len(new_alias) > 50:
                raise HTTPException(
                    status_code=400,
                    detail="Alias must be between 3 and 50 characters"
                )

            # Set new alias
            ALIASES[new_alias] = session_id

        # Update collection
        collection["alias"] = new_alias
        collection["updated_at"] = datetime.utcnow().isoformat() + "Z"

        logger.info(f"Updated alias for {session_id}: {old_alias} -> {new_alias}")

        return UpdateAliasResponse(
            success=True,
            session_id=session_id,
            alias=new_alias
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update alias: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/{session_id}/password", response_model=UpdatePasswordResponse)
async def update_collection_password(session_id: str, request: UpdatePasswordRequest):
    """Update collection password.

    Args:
        session_id: Collection ID
        request: Password update request

    Returns:
        Update result

    Raises:
        HTTPException: If collection not found or user not owner
    """
    try:
        if session_id not in COLLECTIONS:
            raise HTTPException(status_code=404, detail="Collection not found")

        collection = COLLECTIONS[session_id]

        # Verify user is owner
        if collection["owner_username"] != request.admin_username:
            raise HTTPException(
                status_code=403,
                detail="Only owner can update password"
            )

        # Update password
        collection["admin_password_hash"] = request.new_password_hash
        collection["has_password"] = bool(request.new_password_hash)
        collection["updated_at"] = datetime.utcnow().isoformat() + "Z"

        logger.info(f"Updated password for collection: {session_id}")

        return UpdatePasswordResponse(
            success=True,
            message="Password updated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update password: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/{session_id}/start-talk", response_model=StartTalkResponse)
async def start_talk(session_id: str, request: StartTalkRequest):
    """Create a new talk in collection.

    Args:
        session_id: Collection ID
        request: Talk creation request

    Returns:
        Created talk information

    Raises:
        HTTPException: If collection not found
    """
    try:
        if session_id not in COLLECTIONS:
            raise HTTPException(status_code=404, detail="Collection not found")

        collection = COLLECTIONS[session_id]

        # Generate talk ID
        import uuid
        talk_id = str(uuid.uuid4())

        # Create talk
        talk = {
            "talk_id": talk_id,
            "title": request.title,
            "description": request.description,
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "slide_count": 0
        }

        # Add to collection
        collection["talks"].append(talk)
        collection["updated_at"] = datetime.utcnow().isoformat() + "Z"

        logger.info(f"Created talk {talk_id} in collection {session_id}")

        return StartTalkResponse(
            success=True,
            talk=talk
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create talk: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/{session_id}/upload-slide")
async def upload_slide(
    session_id: str,
    slide_number: int,
    # file: UploadFile = File(...) # Commented out for now - needs proper file handling
):
    """Upload a slide to collection.

    Args:
        session_id: Collection ID
        slide_number: Slide sequence number

    Returns:
        Upload result

    Raises:
        HTTPException: If collection not found
    """
    # TODO: Implement proper file upload handling
    # This is a placeholder implementation

    if session_id not in COLLECTIONS:
        raise HTTPException(status_code=404, detail="Collection not found")

    logger.info(f"Slide upload for collection {session_id}, slide #{slide_number}")

    return {
        "success": True,
        "slide_id": f"slide-{slide_number}",
        "slide_number": slide_number
    }


# Initialize function

def get_cloud_router() -> APIRouter:
    """Get the cloud API router.

    Returns:
        Configured API router
    """
    return router
