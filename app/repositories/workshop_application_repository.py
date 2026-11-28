"""Repository for persisting and querying household WorkshopApplication records."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.workshop import WorkshopApplication, WorkshopApplicationStatus


class WorkshopApplicationRepository:
    """Database persistence layer for workshop_applications records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def slug_exists(self, slug: str) -> bool:
        """Return True if a workshop application already claims the given proposed_slug."""
        existing = self._session.scalar(
            select(WorkshopApplication.id).where(WorkshopApplication.proposed_slug == slug)
        )
        return existing is not None

    def application_code_exists(self, code: str) -> bool:
        """Return True if a workshop application already uses the given application_code."""
        existing = self._session.scalar(
            select(WorkshopApplication.id).where(WorkshopApplication.application_code == code)
        )
        return existing is not None

    def count_applications(self) -> int:
        """Return the total number of workshop applications for sequential code generation."""
        count = self._session.scalar(select(func.count(WorkshopApplication.id)))
        return int(count or 0)

    def create_application(
        self,
        *,
        application_code: str,
        user_id: uuid.UUID,
        proposed_slug: str,
        name_vi: str,
        name_en: str | None,
        tagline_vi: str | None,
        tagline_en: str | None,
        artisan_name: str,
        phone: str,
        address_vi: str,
        address_en: str | None,
        history_vi: str,
        history_en: str | None,
        opening_hours: str,
        is_open_now: bool,
        has_experience: bool,
        experience_desc_vi: str | None,
        experience_desc_en: str | None,
        latitude: Decimal | None,
        longitude: Decimal | None,
        workshop_media_ids: list[str],
        certificate_media_ids: list[str],
    ) -> WorkshopApplication:
        """Stage a new Pending WorkshopApplication row in the current DB transaction."""
        application = WorkshopApplication(
            application_code=application_code,
            user_id=user_id,
            proposed_slug=proposed_slug,
            name_vi=name_vi,
            name_en=name_en,
            tagline_vi=tagline_vi,
            tagline_en=tagline_en,
            artisan_name=artisan_name,
            phone=phone,
            address_vi=address_vi,
            address_en=address_en,
            history_vi=history_vi,
            history_en=history_en,
            opening_hours=opening_hours,
            is_open_now=is_open_now,
            has_experience=has_experience,
            experience_desc_vi=experience_desc_vi,
            experience_desc_en=experience_desc_en,
            latitude=latitude,
            longitude=longitude,
            workshop_media_ids=workshop_media_ids,
            certificate_media_ids=certificate_media_ids,
            status=WorkshopApplicationStatus.PENDING.value,
        )
        self._session.add(application)
        self._session.flush()
        return application

    def commit(self) -> None:
        """Commit the current database transaction."""
        self._session.commit()

    def rollback(self) -> None:
        """Rollback the current database transaction."""
        self._session.rollback()
