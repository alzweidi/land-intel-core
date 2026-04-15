from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.models import SourceSnapshot


def list_source_snapshots(session: Session, *, limit: int = 100) -> list[SourceSnapshot]:
    stmt = (
        select(SourceSnapshot)
        .options(selectinload(SourceSnapshot.raw_assets))
        .order_by(SourceSnapshot.acquired_at.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


def get_source_snapshot(session: Session, *, snapshot_id: UUID) -> SourceSnapshot | None:
    stmt = (
        select(SourceSnapshot)
        .options(selectinload(SourceSnapshot.raw_assets))
        .where(SourceSnapshot.id == snapshot_id)
    )
    return session.execute(stmt).scalar_one_or_none()

