from sqlalchemy import TIMESTAMP, ForeignKey, SmallInteger, String
from sqlalchemy.orm import mapped_column

from models import Base
from utils import timing


class GenerationRunRow(Base):
    """Durable journal of one chat generation call.

    `side_effects` is reserved for the tool era: once a W/RW effect has been
    recorded for a run, retrying it from scratch is forbidden (see PLAN.md 2.7).
    """

    __tablename__ = "generation_run"

    # PLAN-NOTE(2.7): extend with checkpoint/snapshot columns when the deferred
    # orchestrator checkpoint model (Phase 5) lands; do not repurpose status.
    thread_id = mapped_column(
        String(36), ForeignKey("thread.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = mapped_column(
        String(36), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status = mapped_column(String(20), nullable=False, default="running", index=True)
    side_effects = mapped_column(SmallInteger, nullable=False, default=0)
    creation_date = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=timing.get_utc_now
    )
    update_time = mapped_column(TIMESTAMP(timezone=True), nullable=True)


__all__ = ["GenerationRunRow"]
