"""Collection registry for managing persistent collections across devices."""

import logging
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import uuid
import threading
import random
import string

logger = logging.getLogger(__name__)


def generate_collection_id() -> str:
    """Generate a unique local collection ID.

    Format: CLT-XXX-XXX (e.g., CLT-ABC-123)

    Returns:
        Collection ID string
    """
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=3))
    return f"CLT-{letters}-{numbers}"


@dataclass
class Collection:
    """Represents a collection of talks."""

    collection_id: str  # Local ID (CLT-XXX-XXX)
    cloud_collection_id: str  # Cloud ID (e.g., AUA-6538)
    name: str
    owner_username: str
    is_owner: bool
    access_level: str  # "owner" or "contributor"
    created_at: str
    last_accessed: str
    alias: Optional[str] = None  # User-friendly alias
    has_password: bool = False  # Whether collection has password for sharing

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Collection':
        """Create from dictionary."""
        return cls(**data)


class CollectionRegistry:
    """Manages the local registry of collections."""

    def __init__(self, registry_path: Optional[Path] = None):
        """Initialize collection registry.

        Args:
            registry_path: Path to collections.yaml (default: ~/.config/seenslide/collections.yaml)
        """
        if registry_path is None:
            config_dir = Path.home() / ".config" / "seenslide"
            config_dir.mkdir(parents=True, exist_ok=True)
            registry_path = config_dir / "collections.yaml"

        self.registry_path = registry_path
        self._lock = threading.Lock()

        # Load or initialize registry
        self._load_registry()

        logger.info(f"CollectionRegistry initialized: {self.registry_path}")

    def _load_registry(self):
        """Load registry from disk."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r') as f:
                    data = yaml.safe_load(f) or {}

                self.collections = [
                    Collection.from_dict(c) for c in data.get('collections', [])
                ]
                self.current_collection_id = data.get('current_collection_id')

                logger.info(f"Loaded {len(self.collections)} collections from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
                self.collections = []
                self.current_collection_id = None
        else:
            self.collections = []
            self.current_collection_id = None
            logger.info("No existing registry found, starting fresh")

    def _save_registry(self):
        """Save registry to disk."""
        try:
            data = {
                'collections': [c.to_dict() for c in self.collections],
                'current_collection_id': self.current_collection_id
            }

            # Write to temp file first (atomic write)
            temp_path = self.registry_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)

            # Move temp file to actual file
            temp_path.replace(self.registry_path)

            logger.debug(f"Saved registry with {len(self.collections)} collections")
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")
            raise

    def add_collection(
        self,
        cloud_collection_id: str,
        name: str,
        owner_username: str,
        is_owner: bool,
        access_level: str = "owner",
        alias: Optional[str] = None,
        has_password: bool = False
    ) -> Collection:
        """Add a new collection to the registry.

        Args:
            cloud_collection_id: Cloud collection ID
            name: Collection name
            owner_username: Username of the owner
            is_owner: Whether current user is the owner
            access_level: "owner" or "contributor"
            alias: Optional user-friendly alias
            has_password: Whether collection has password set

        Returns:
            Created Collection object
        """
        with self._lock:
            # Generate local collection ID
            collection_id = generate_collection_id()

            # Create collection object
            now = datetime.utcnow().isoformat() + 'Z'
            collection = Collection(
                collection_id=collection_id,
                cloud_collection_id=cloud_collection_id,
                name=name,
                owner_username=owner_username,
                is_owner=is_owner,
                access_level=access_level,
                alias=alias,
                has_password=has_password,
                created_at=now,
                last_accessed=now
            )

            self.collections.append(collection)

            # Set as current if first collection
            if len(self.collections) == 1:
                self.current_collection_id = collection_id

            self._save_registry()

            logger.info(f"Added collection: {collection_id} ({cloud_collection_id})")
            return collection

    def get_collection(self, collection_id: str) -> Optional[Collection]:
        """Get collection by local ID.

        Args:
            collection_id: Local collection ID

        Returns:
            Collection object or None
        """
        for collection in self.collections:
            if collection.collection_id == collection_id:
                return collection
        return None

    def get_collection_by_cloud_id(self, cloud_collection_id: str) -> Optional[Collection]:
        """Get collection by cloud ID.

        Args:
            cloud_collection_id: Cloud collection ID

        Returns:
            Collection object or None
        """
        for collection in self.collections:
            if collection.cloud_collection_id == cloud_collection_id:
                return collection
        return None

    def get_collection_by_alias(self, alias: str) -> Optional[Collection]:
        """Get collection by alias.

        Args:
            alias: Collection alias

        Returns:
            Collection object or None
        """
        for collection in self.collections:
            if collection.alias and collection.alias.lower() == alias.lower():
                return collection
        return None

    def list_collections(self) -> List[Collection]:
        """Get all collections.

        Returns:
            List of Collection objects
        """
        return self.collections.copy()

    def get_current_collection(self) -> Optional[Collection]:
        """Get the current active collection.

        Returns:
            Current Collection object or None
        """
        if self.current_collection_id:
            return self.get_collection(self.current_collection_id)
        return None

    def set_current_collection(self, collection_id: str) -> bool:
        """Set the current active collection.

        Args:
            collection_id: Local collection ID to set as current

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            # Verify collection exists
            collection = self.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return False

            # Update last accessed time
            collection.last_accessed = datetime.utcnow().isoformat() + 'Z'

            # Set as current
            self.current_collection_id = collection_id
            self._save_registry()

            logger.info(f"Set current collection: {collection_id}")
            return True

    def update_collection(
        self,
        collection_id: str,
        name: Optional[str] = None,
        alias: Optional[str] = None,
        has_password: Optional[bool] = None
    ) -> bool:
        """Update collection metadata.

        Args:
            collection_id: Local collection ID
            name: New name (optional)
            alias: New alias (optional)
            has_password: Whether password is set (optional)

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            collection = self.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return False

            # Update fields
            if name is not None:
                collection.name = name
            if alias is not None:
                collection.alias = alias
            if has_password is not None:
                collection.has_password = has_password

            collection.last_accessed = datetime.utcnow().isoformat() + 'Z'

            self._save_registry()
            logger.info(f"Updated collection: {collection_id}")
            return True

    def remove_collection(self, collection_id: str) -> bool:
        """Remove a collection from the registry.

        Args:
            collection_id: Local collection ID

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            # Find and remove collection
            for i, collection in enumerate(self.collections):
                if collection.collection_id == collection_id:
                    self.collections.pop(i)

                    # Update current if needed
                    if self.current_collection_id == collection_id:
                        if self.collections:
                            # Switch to most recent collection
                            most_recent = max(
                                self.collections,
                                key=lambda c: c.last_accessed
                            )
                            self.current_collection_id = most_recent.collection_id
                        else:
                            self.current_collection_id = None

                    self._save_registry()
                    logger.info(f"Removed collection: {collection_id}")
                    return True

            logger.error(f"Collection not found: {collection_id}")
            return False

    def has_collections(self) -> bool:
        """Check if any collections exist.

        Returns:
            True if at least one collection exists
        """
        return len(self.collections) > 0
