"""Session management API endpoints."""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from core.models.session import Session
from modules.web.dependencies import get_db_provider

logger = logging.getLogger(__name__)

router = APIRouter()


class SessionCreate(BaseModel):
    """Request model for creating a session."""
    name: str
    description: Optional[str] = ""
    presenter_name: Optional[str] = ""
    capture_interval_seconds: Optional[float] = 2.0
    dedup_strategy: Optional[str] = "hash"


class SessionUpdate(BaseModel):
    """Request model for updating a session."""
    name: Optional[str] = None
    description: Optional[str] = None
    presenter_name: Optional[str] = None
    status: Optional[str] = None
    total_slides: Optional[int] = None


class SessionResponse(BaseModel):
    """Response model for session data."""
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    name: str
    description: str
    presenter_name: str
    start_time: Optional[float]
    end_time: Optional[float]
    status: str
    total_slides: int
    capture_interval_seconds: float
    dedup_strategy: str


@router.post("/", response_model=SessionResponse, status_code=201)
async def create_session(session_data: SessionCreate, request: Request):
    """Create a new session.

    Args:
        session_data: Session creation data
        request: FastAPI request object

    Returns:
        Created session

    Raises:
        HTTPException: If session creation fails
    """
    try:
        db_provider = get_db_provider(request)

        # Create session object
        session = Session(
            name=session_data.name,
            description=session_data.description or "",
            presenter_name=session_data.presenter_name or "",
            capture_interval_seconds=session_data.capture_interval_seconds or 2.0,
            dedup_strategy=session_data.dedup_strategy or "hash"
        )

        # Save to database
        db_provider.create_session(session)

        logger.info(f"Created session: {session.session_id}")
        return SessionResponse.model_validate(session)

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[SessionResponse])
async def list_sessions(request: Request):
    """List all sessions.

    Args:
        request: FastAPI request object

    Returns:
        List of sessions

    Raises:
        HTTPException: If listing fails
    """
    try:
        # Note: This would require adding a list_sessions method to SQLiteStorageProvider
        # For now, return empty list
        logger.warning("list_sessions not fully implemented")
        return []

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request: Request):
    """Get a specific session.

    Args:
        session_id: Session UUID
        request: FastAPI request object

    Returns:
        Session data

    Raises:
        HTTPException: If session not found or retrieval fails
    """
    try:
        db_provider = get_db_provider(request)
        session = db_provider.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionResponse.model_validate(session)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    session_data: SessionUpdate,
    request: Request
):
    """Update a session.

    Args:
        session_id: Session UUID
        session_data: Session update data
        request: FastAPI request object

    Returns:
        Updated session

    Raises:
        HTTPException: If session not found or update fails
    """
    try:
        db_provider = get_db_provider(request)

        # Get existing session
        session = db_provider.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Update fields
        if session_data.name is not None:
            session.name = session_data.name
        if session_data.description is not None:
            session.description = session_data.description
        if session_data.presenter_name is not None:
            session.presenter_name = session_data.presenter_name
        if session_data.status is not None:
            session.status = session_data.status
        if session_data.total_slides is not None:
            session.total_slides = session_data.total_slides

        # Save updates
        success = db_provider.update_session(session)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update session")

        logger.info(f"Updated session: {session_id}")
        return SessionResponse.model_validate(session)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request):
    """Delete a session.

    Args:
        session_id: Session UUID
        request: FastAPI request object

    Raises:
        HTTPException: If session not found or deletion fails
    """
    try:
        # Note: This would require adding delete methods to storage providers
        # For now, just log
        logger.warning(f"delete_session not fully implemented: {session_id}")
        raise HTTPException(status_code=501, detail="Not implemented")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(status_code=500, detail=str(e))
