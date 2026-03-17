from sqlalchemy import String, Text, DateTime, JSON, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.core.database import Base

class JobCard(Base):
    """Model for storing scraped job cards."""
    __tablename__ = "job_cards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(50), index=True)
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="captured")
    html_content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<JobCard(id={self.id}, event_id='{self.event_id}', url='{self.url[:30]}...')>"
