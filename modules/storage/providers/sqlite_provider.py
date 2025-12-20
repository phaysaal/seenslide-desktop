"""SQLite-based storage provider for slide metadata."""

import logging
import sqlite3
from pathlib import Path
from typing import Optional, List
import json

from core.interfaces.storage import IStorageProvider, StorageError
from core.models.slide import ProcessedSlide
from core.models.session import Session

logger = logging.getLogger(__name__)


class SQLiteStorageProvider(IStorageProvider):
    """Storage provider using SQLite for metadata.

    This provider handles:
    - Storing session metadata
    - Storing slide metadata
    - Querying sessions and slides
    """

    def __init__(self):
        """Initialize the SQLite storage provider."""
        self._config = {}
        self._initialized = False
        self._db_path = None
        self._conn = None

    def initialize(self, config: dict) -> bool:
        """Initialize storage provider with configuration.

        Args:
            config: Dictionary containing configuration:
                - base_path: str, base directory for database
                - database_subdir: str, subdirectory for database (default: 'db')
                - database_filename: str, database filename (default: 'seenslide.db')

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self._config = config

            # Determine database path
            base_path = Path(config.get('base_path', '/tmp/seenslide'))
            db_subdir = config.get('database_subdir', 'db')
            db_filename = config.get('database_filename', 'seenslide.db')

            db_dir = base_path / db_subdir
            db_dir.mkdir(parents=True, exist_ok=True)

            self._db_path = db_dir / db_filename

            # Connect to database
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

            # Create tables
            self._create_tables()

            self._initialized = True
            logger.info(f"SQLite storage initialized at: {self._db_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize SQLite storage: {e}")
            return False

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        cursor = self._conn.cursor()

        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                presenter_name TEXT,
                start_time REAL,
                end_time REAL,
                status TEXT NOT NULL,
                total_slides INTEGER DEFAULT 0,
                capture_interval_seconds REAL,
                dedup_strategy TEXT,
                metadata TEXT
            )
        """)

        # Slides table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS slides (
                slide_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                image_path TEXT,
                thumbnail_path TEXT,
                width INTEGER,
                height INTEGER,
                file_size_bytes INTEGER,
                image_hash TEXT,
                similarity_score REAL,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_slides_session
            ON slides(session_id, sequence_number)
        """)

        self._conn.commit()

    def create_session(self, session: Session) -> str:
        """Create a new session in the database.

        Args:
            session: Session object to create

        Returns:
            Session ID

        Raises:
            StorageError: If session creation fails
        """
        if not self._initialized:
            raise StorageError("Provider not initialized")

        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (
                    session_id, name, description, presenter_name,
                    start_time, end_time, status, total_slides,
                    capture_interval_seconds, dedup_strategy, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_id,
                session.name,
                session.description,
                session.presenter_name,
                session.start_time,
                session.end_time,
                session.status,
                session.total_slides,
                session.capture_interval_seconds,
                session.dedup_strategy,
                json.dumps(session.metadata)
            ))
            self._conn.commit()

            logger.info(f"Created session in database: {session.session_id}")
            return session.session_id

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise StorageError(f"Failed to create session: {e}")

    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve session by ID.

        Args:
            session_id: UUID of the session

        Returns:
            Session object or None if not found
        """
        if not self._initialized:
            return None

        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            # Convert row to Session object
            return Session(
                session_id=row['session_id'],
                name=row['name'],
                description=row['description'] or "",
                presenter_name=row['presenter_name'] or "",
                start_time=row['start_time'],
                end_time=row['end_time'],
                status=row['status'],
                total_slides=row['total_slides'],
                capture_interval_seconds=row['capture_interval_seconds'],
                dedup_strategy=row['dedup_strategy'] or "hash",
                metadata=json.loads(row['metadata']) if row['metadata'] else {}
            )

        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None

    def get_all_sessions(self) -> List[Session]:
        """Retrieve all sessions.

        Returns:
            List of Session objects
        """
        if not self._initialized:
            return []

        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions ORDER BY start_time DESC"
            )
            rows = cursor.fetchall()

            sessions = []
            for row in rows:
                session = Session(
                    session_id=row['session_id'],
                    name=row['name'],
                    description=row['description'] or "",
                    presenter_name=row['presenter_name'] or "",
                    start_time=row['start_time'],
                    end_time=row['end_time'],
                    status=row['status'],
                    total_slides=row['total_slides'],
                    capture_interval_seconds=row['capture_interval_seconds'],
                    dedup_strategy=row['dedup_strategy'] or "hash",
                    metadata=json.loads(row['metadata']) if row['metadata'] else {}
                )
                sessions.append(session)

            return sessions

        except Exception as e:
            logger.error(f"Failed to get all sessions: {e}")
            return []

    def get_session_slides(self, session_id: str, limit: int = 100, offset: int = 0) -> List[ProcessedSlide]:
        """Get slides for a specific session.

        Args:
            session_id: Session ID
            limit: Maximum number of slides to return
            offset: Number of slides to skip

        Returns:
            List of ProcessedSlide objects
        """
        return self.list_slides(session_id=session_id, limit=limit, offset=offset)

    def update_session(self, session: Session) -> bool:
        """Update an existing session.

        Args:
            session: Session object with updated data

        Returns:
            True if update successful, False otherwise
        """
        if not self._initialized:
            return False

        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE sessions SET
                    name = ?,
                    description = ?,
                    presenter_name = ?,
                    start_time = ?,
                    end_time = ?,
                    status = ?,
                    total_slides = ?,
                    capture_interval_seconds = ?,
                    dedup_strategy = ?,
                    metadata = ?
                WHERE session_id = ?
            """, (
                session.name,
                session.description,
                session.presenter_name,
                session.start_time,
                session.end_time,
                session.status,
                session.total_slides,
                session.capture_interval_seconds,
                session.dedup_strategy,
                json.dumps(session.metadata),
                session.session_id
            ))
            self._conn.commit()

            logger.debug(f"Updated session: {session.session_id}")
            return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"Failed to update session: {e}")
            return False

    def save_slide(self, slide: ProcessedSlide) -> str:
        """Save a processed slide to database.

        Args:
            slide: ProcessedSlide object to save

        Returns:
            Slide ID

        Raises:
            StorageError: If save fails
        """
        if not self._initialized:
            raise StorageError("Provider not initialized")

        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO slides (
                    slide_id, session_id, sequence_number, timestamp,
                    image_path, thumbnail_path, width, height,
                    file_size_bytes, image_hash, similarity_score, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                slide.slide_id,
                slide.session_id,
                slide.sequence_number,
                slide.timestamp,
                slide.image_path,
                slide.thumbnail_path,
                slide.width,
                slide.height,
                slide.file_size_bytes,
                slide.image_hash,
                slide.similarity_score,
                json.dumps(slide.metadata)
            ))
            self._conn.commit()

            logger.debug(f"Saved slide to database: {slide.slide_id}")
            return slide.slide_id

        except Exception as e:
            logger.error(f"Failed to save slide: {e}")
            raise StorageError(f"Failed to save slide: {e}")

    def get_slide(self, slide_id: str) -> Optional[ProcessedSlide]:
        """Retrieve slide by ID.

        Args:
            slide_id: UUID of the slide

        Returns:
            ProcessedSlide object or None if not found
        """
        if not self._initialized:
            return None

        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM slides WHERE slide_id = ?",
                (slide_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_slide(row)

        except Exception as e:
            logger.error(f"Failed to get slide: {e}")
            return None

    def list_slides(
        self,
        session_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[ProcessedSlide]:
        """List slides for a session.

        Args:
            session_id: UUID of the session
            limit: Maximum number of slides to return
            offset: Number of slides to skip

        Returns:
            List of ProcessedSlide objects
        """
        if not self._initialized:
            return []

        try:
            cursor = self._conn.cursor()
            query = """
                SELECT * FROM slides
                WHERE session_id = ?
                ORDER BY sequence_number
            """

            if limit is not None:
                query += f" LIMIT {limit} OFFSET {offset}"

            cursor.execute(query, (session_id,))
            rows = cursor.fetchall()

            return [self._row_to_slide(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to list slides: {e}")
            return []

    def get_slide_count(self, session_id: str) -> int:
        """Get total slide count for session.

        Args:
            session_id: UUID of the session

        Returns:
            Total number of slides
        """
        if not self._initialized:
            return 0

        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM slides WHERE session_id = ?",
                (session_id,)
            )
            return cursor.fetchone()[0]

        except Exception as e:
            logger.error(f"Failed to count slides: {e}")
            return 0

    def cleanup(self) -> None:
        """Clean up resources."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._initialized = False
        logger.debug("SQLite storage cleaned up")

    @property
    def name(self) -> str:
        """Provider name."""
        return "sqlite"

    def _row_to_slide(self, row: sqlite3.Row) -> ProcessedSlide:
        """Convert database row to ProcessedSlide object.

        Args:
            row: Database row

        Returns:
            ProcessedSlide object
        """
        return ProcessedSlide(
            slide_id=row['slide_id'],
            session_id=row['session_id'],
            image_path=row['image_path'] or "",
            thumbnail_path=row['thumbnail_path'] or "",
            timestamp=row['timestamp'],
            sequence_number=row['sequence_number'],
            width=row['width'] or 0,
            height=row['height'] or 0,
            file_size_bytes=row['file_size_bytes'] or 0,
            image_hash=row['image_hash'] or "",
            similarity_score=row['similarity_score'] or 0.0,
            metadata=json.loads(row['metadata']) if row['metadata'] else {}
        )
