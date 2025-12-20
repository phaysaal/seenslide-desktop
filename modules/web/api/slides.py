"""Slide retrieval API endpoints."""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from pathlib import Path

from core.models.slide import ProcessedSlide
from modules.web.dependencies import get_db_provider, get_fs_provider

logger = logging.getLogger(__name__)

router = APIRouter()


class SlideResponse(BaseModel):
    """Response model for slide data."""
    model_config = ConfigDict(from_attributes=True)

    slide_id: str
    session_id: str
    sequence_number: int
    timestamp: float
    image_path: str
    thumbnail_path: str
    width: int
    height: int
    file_size_bytes: int
    image_hash: str
    similarity_score: float


@router.get("/{session_id}", response_model=List[SlideResponse])
async def list_slides(
    session_id: str,
    request: Request,
    limit: Optional[int] = None,
    offset: int = 0
):
    """List slides for a session.

    Args:
        session_id: Session UUID
        request: FastAPI request object
        limit: Maximum number of slides to return
        offset: Number of slides to skip

    Returns:
        List of slides

    Raises:
        HTTPException: If listing fails
    """
    try:
        db_provider = get_db_provider(request)
        slides = db_provider.list_slides(session_id, limit=limit, offset=offset)

        return [SlideResponse.model_validate(slide) for slide in slides]

    except Exception as e:
        logger.error(f"Failed to list slides: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/count")
async def get_slide_count(session_id: str, request: Request):
    """Get total slide count for a session.

    Args:
        session_id: Session UUID
        request: FastAPI request object

    Returns:
        Dictionary with slide count

    Raises:
        HTTPException: If count retrieval fails
    """
    try:
        db_provider = get_db_provider(request)
        count = db_provider.get_slide_count(session_id)

        return {"session_id": session_id, "count": count}

    except Exception as e:
        logger.error(f"Failed to get slide count: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/slide/{slide_id}", response_model=SlideResponse)
async def get_slide(slide_id: str, request: Request):
    """Get a specific slide.

    Args:
        slide_id: Slide UUID
        request: FastAPI request object

    Returns:
        Slide data

    Raises:
        HTTPException: If slide not found or retrieval fails
    """
    try:
        db_provider = get_db_provider(request)
        slide = db_provider.get_slide(slide_id)

        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        return SlideResponse.model_validate(slide)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get slide: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/image/{slide_id}")
async def get_slide_image(slide_id: str, request: Request):
    """Get the full-size image for a slide.

    Args:
        slide_id: Slide UUID
        request: FastAPI request object

    Returns:
        Image file

    Raises:
        HTTPException: If slide or image not found
    """
    try:
        db_provider = get_db_provider(request)
        slide = db_provider.get_slide(slide_id)

        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        image_path = Path(slide.image_path)
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="Image file not found")

        return FileResponse(
            path=str(image_path),
            media_type="image/png",
            filename=f"{slide_id}.png"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get slide image: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thumbnail/{slide_id}")
async def get_slide_thumbnail(slide_id: str, request: Request):
    """Get the thumbnail image for a slide.

    Args:
        slide_id: Slide UUID
        request: FastAPI request object

    Returns:
        Thumbnail image file

    Raises:
        HTTPException: If slide or thumbnail not found
    """
    try:
        db_provider = get_db_provider(request)
        slide = db_provider.get_slide(slide_id)

        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        if not slide.thumbnail_path:
            raise HTTPException(status_code=404, detail="Thumbnail not available")

        thumbnail_path = Path(slide.thumbnail_path)
        if not thumbnail_path.exists():
            raise HTTPException(status_code=404, detail="Thumbnail file not found")

        return FileResponse(
            path=str(thumbnail_path),
            media_type="image/jpeg",
            filename=f"{slide_id}_thumb.jpg"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get slide thumbnail: {e}")
        raise HTTPException(status_code=500, detail=str(e))
