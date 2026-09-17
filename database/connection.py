"""
HELIOS Database Connection Manager

Provides SQLAlchemy engine, session factory, and database initialization.
Supports both SQLite (development) and PostgreSQL (production).
"""

import os
from typing import Optional, Generator
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import logging

from .schema.helios_schema import Base, create_all_tables, drop_all_tables


logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration"""

    def __init__(
        self,
        database_url: Optional[str] = None,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10
    ):
        """
        Initialize database configuration.

        Args:
            database_url: SQLAlchemy database URL (default: from env or SQLite)
            echo: Echo SQL statements to logs
            pool_size: Connection pool size (PostgreSQL only)
            max_overflow: Max overflow connections (PostgreSQL only)
        """
        self.database_url = database_url or self._get_default_url()
        self.echo = echo
        self.pool_size = pool_size
        self.max_overflow = max_overflow

    def _get_default_url(self) -> str:
        """Get default database URL from environment or use SQLite."""
        # Check environment variable
        env_url = os.getenv('HELIOS_DATABASE_URL')
        if env_url:
            return env_url

        # Default to SQLite in data directory
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'data',
            'helios.db'
        )
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return f'sqlite:///{db_path}'

    def is_sqlite(self) -> bool:
        """Check if using SQLite."""
        return self.database_url.startswith('sqlite')


class DatabaseManager:
    """
    Database connection and session manager.

    Usage:
        # Initialize once at application startup
        db_manager = DatabaseManager()
        db_manager.initialize()

        # Use sessions
        with db_manager.get_session() as session:
            forecast = session.query(Forecast).first()
            ...
    """

    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        Initialize database manager.

        Args:
            config: Database configuration (default: auto-detect from env)
        """
        self.config = config or DatabaseConfig()
        self._engine = None
        self._session_factory = None

    @property
    def engine(self):
        """Get SQLAlchemy engine (lazy initialization)."""
        if self._engine is None:
            self._create_engine()
        return self._engine

    @property
    def session_factory(self):
        """Get session factory (lazy initialization)."""
        if self._session_factory is None:
            self._create_session_factory()
        return self._session_factory

    def _create_engine(self):
        """Create SQLAlchemy engine."""
        logger.info(f"Creating database engine: {self._mask_url(self.config.database_url)}")

        if self.config.is_sqlite():
            # SQLite configuration
            self._engine = create_engine(
                self.config.database_url,
                echo=self.config.echo,
                connect_args={'check_same_thread': False},
                poolclass=StaticPool
            )

            # Enable foreign keys for SQLite
            @event.listens_for(self._engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        else:
            # PostgreSQL configuration
            self._engine = create_engine(
                self.config.database_url,
                echo=self.config.echo,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_pre_ping=True  # Verify connections before use
            )

        logger.info("Database engine created successfully")

    def _create_session_factory(self):
        """Create session factory."""
        self._session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )
        logger.info("Session factory created successfully")

    def initialize(self, create_tables: bool = True):
        """
        Initialize database.

        Args:
            create_tables: Create all tables if they don't exist
        """
        logger.info("Initializing database")

        # Ensure engine and session factory are created
        _ = self.engine
        _ = self.session_factory

        if create_tables:
            logger.info("Creating database tables")
            create_all_tables(self.engine)
            logger.info("Database tables created successfully")

        logger.info("Database initialization complete")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get database session as context manager.

        Yields:
            SQLAlchemy Session

        Example:
            with db_manager.get_session() as session:
                forecast = session.query(Forecast).first()
                ...
        """
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def drop_all_tables(self):
        """
        Drop all tables (CAUTION: destructive operation!).

        Use only for testing or complete database reset.
        """
        logger.warning("Dropping all database tables")
        drop_all_tables(self.engine)
        logger.info("All tables dropped")

    def recreate_tables(self):
        """
        Drop and recreate all tables (CAUTION: destructive!).

        Use only for development/testing.
        """
        logger.warning("Recreating all database tables")
        self.drop_all_tables()
        create_all_tables(self.engine)
        logger.info("All tables recreated")

    def close(self):
        """Close database connections."""
        if self._engine:
            logger.info("Closing database connections")
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connections closed")

    @staticmethod
    def _mask_url(url: str) -> str:
        """Mask sensitive information in database URL."""
        if '@' in url:
            # Mask password in URL
            parts = url.split('@')
            credentials = parts[0].split('://')
            if len(credentials) > 1 and ':' in credentials[1]:
                user = credentials[1].split(':')[0]
                masked = f"{credentials[0]}://{user}:****@{parts[1]}"
                return masked
        return url


# Global database manager instance (singleton pattern)
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """
    Get global database manager instance.

    Returns:
        DatabaseManager singleton
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        _db_manager.initialize()
    return _db_manager


def get_session() -> Generator[Session, None, None]:
    """
    Get database session (convenience function).

    Yields:
        SQLAlchemy Session

    Example:
        with get_session() as session:
            forecast = session.query(Forecast).first()
            ...
    """
    manager = get_db_manager()
    with manager.get_session() as session:
        yield session


# Context manager for session (alternative syntax)
@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Provide a transactional scope for database operations.

    Yields:
        SQLAlchemy Session

    Example:
        with session_scope() as session:
            session.add(forecast)
            # Automatically commits on success, rolls back on error
    """
    manager = get_db_manager()
    with manager.get_session() as session:
        yield session
