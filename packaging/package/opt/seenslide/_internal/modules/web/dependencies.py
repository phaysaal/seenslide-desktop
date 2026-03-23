"""Dependency injection for FastAPI endpoints."""

from fastapi import Request
from modules.storage.providers.sqlite_provider import SQLiteStorageProvider
from modules.storage.providers.filesystem_provider import FilesystemStorageProvider
from core.bus.event_bus import EventBus


def get_app_state(request: Request):
    """Get application state from request.

    Args:
        request: FastAPI request object

    Returns:
        AppState instance
    """
    return request.app.state.app_state


def get_db_provider(request: Request) -> SQLiteStorageProvider:
    """Get database provider from request.

    Args:
        request: FastAPI request object

    Returns:
        SQLiteStorageProvider instance
    """
    app_state = get_app_state(request)
    return app_state.get_db_provider()


def get_fs_provider(request: Request) -> FilesystemStorageProvider:
    """Get filesystem provider from request.

    Args:
        request: FastAPI request object

    Returns:
        FilesystemStorageProvider instance
    """
    app_state = get_app_state(request)
    return app_state.get_fs_provider()


def get_event_bus(request: Request) -> EventBus:
    """Get event bus from request.

    Args:
        request: FastAPI request object

    Returns:
        EventBus instance
    """
    app_state = get_app_state(request)
    return app_state.get_event_bus()
