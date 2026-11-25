"""Database health repository using database-independent SQLAlchemy expressions."""

from sqlalchemy import literal, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


class HealthRepository:
    """Checks database connectivity through an ORM session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def ping(self) -> bool:
        """Execute a portable SQLAlchemy query to verify database liveness."""
        try:
            result = self._session.execute(select(literal(1))).scalar_one()
        except SQLAlchemyError:
            return False
        return result == 1
