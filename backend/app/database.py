from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

DATABASE_FILE = DATA_DIR / "reel2career.db"

DATABASE_URL = (
    f"sqlite:///{DATABASE_FILE.as_posix()}"
)


# ============================================================
# DATABASE ENGINE
# ============================================================

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# ============================================================
# BASE
# ============================================================

class Base(DeclarativeBase):
    pass


# ============================================================
# HELPER
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# REELS
# ============================================================

class Reel(Base):

    __tablename__ = "reels"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    instagram_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    shortcode: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    author: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    media_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unknown",
    )

    media_type: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    caption: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    reel_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    saved_to_reel2career: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # --------------------------------------------------------
    # Processing state
    # --------------------------------------------------------

    metadata_ingested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    thumbnail_ingested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    video_ingested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    carousel_ingested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    transcription_complete: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    ocr_complete: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    ai_analysis_complete: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    resource_verification_complete: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # --------------------------------------------------------
    # Relationships
    # --------------------------------------------------------

    media: Mapped[list["Media"]] = relationship(
        back_populates="reel",
        cascade="all, delete-orphan",
    )

    carousel_slides: Mapped[
        list["CarouselSlide"]
    ] = relationship(
        back_populates="reel",
        cascade="all, delete-orphan",
        order_by="CarouselSlide.position",
    )

    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="reel",
        cascade="all, delete-orphan",
    )

    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="reel",
        cascade="all, delete-orphan",
        uselist=False,
    )

    actions: Mapped[list["Action"]] = relationship(
        back_populates="reel",
        cascade="all, delete-orphan",
    )

    reel_skills: Mapped[list["ReelSkill"]] = relationship(
        back_populates="reel",
        cascade="all, delete-orphan",
    )

    reel_resources: Mapped[
        list["ReelResource"]
    ] = relationship(
        back_populates="reel",
        cascade="all, delete-orphan",
    )

    processing_jobs: Mapped[
        list["ProcessingJob"]
    ] = relationship(
        back_populates="reel",
        cascade="all, delete-orphan",
    )


# ============================================================
# MEDIA
# ============================================================

class Media(Base):

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    reel_id: Mapped[int] = mapped_column(
        ForeignKey(
            "reels.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    media_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    file_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    file_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    checksum: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    reel: Mapped["Reel"] = relationship(
        back_populates="media",
    )


# ============================================================
# CAROUSEL SLIDES
# ============================================================

class CarouselSlide(Base):

    __tablename__ = "carousel_slides"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    reel_id: Mapped[int] = mapped_column(
        ForeignKey(
            "reels.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    file_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    ocr_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    reel: Mapped["Reel"] = relationship(
        back_populates="carousel_slides",
    )

    __table_args__ = (
        UniqueConstraint(
            "reel_id",
            "position",
            name="uq_carousel_reel_position",
        ),
    )


# ============================================================
# EVIDENCE
# ============================================================

class Evidence(Base):

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    reel_id: Mapped[int] = mapped_column(
        ForeignKey(
            "reels.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    evidence_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    source_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    confidence: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    reel: Mapped["Reel"] = relationship(
        back_populates="evidence",
    )


# ============================================================
# ANALYSIS
# ============================================================

class Analysis(Base):

    __tablename__ = "analysis"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    reel_id: Mapped[int] = mapped_column(
        ForeignKey(
            "reels.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    topic: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
    )

    career_area: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
    )

    career_relevance: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    difficulty: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    priority: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    raw_model_output: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    model_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    reel: Mapped["Reel"] = relationship(
        back_populates="analysis",
    )


# ============================================================
# SKILLS
# ============================================================

class Skill(Base):

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    category: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    reel_skills: Mapped[list["ReelSkill"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )


# ============================================================
# REEL ↔ SKILL
# ============================================================

class ReelSkill(Base):

    __tablename__ = "reel_skills"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    reel_id: Mapped[int] = mapped_column(
        ForeignKey(
            "reels.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    skill_id: Mapped[int] = mapped_column(
        ForeignKey(
            "skills.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    relevance: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    required_level: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    reel: Mapped["Reel"] = relationship(
        back_populates="reel_skills",
    )

    skill: Mapped["Skill"] = relationship(
        back_populates="reel_skills",
    )

    __table_args__ = (
        UniqueConstraint(
            "reel_id",
            "skill_id",
            name="uq_reel_skill",
        ),
    )


# ============================================================
# ACTIONS
# ============================================================

class Action(Base):

    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    reel_id: Mapped[int] = mapped_column(
        ForeignKey(
            "reels.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    action_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    priority: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
    )

    estimated_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    reel: Mapped["Reel"] = relationship(
        back_populates="actions",
    )


# ============================================================
# RESOURCES
# ============================================================

class Resource(Base):

    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    url: Mapped[str | None] = mapped_column(
        Text,
        unique=True,
        nullable=True,
        index=True,
    )

    identity_key: Mapped[str | None] = mapped_column(
        String(500),
        unique=True,
        nullable=True,
        index=True,
    )

    resource_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    source_domain: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    verification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unverified",
    )

    http_status: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    last_verified_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    reel_resources: Mapped[
        list["ReelResource"]
    ] = relationship(
        back_populates="resource",
        cascade="all, delete-orphan",
    )


# ============================================================
# REEL ↔ RESOURCE
# ============================================================

class ReelResource(Base):

    __tablename__ = "reel_resources"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    reel_id: Mapped[int] = mapped_column(
        ForeignKey(
            "reels.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    resource_id: Mapped[int] = mapped_column(
        ForeignKey(
            "resources.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    relationship_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    source_evidence_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    source_locator: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    reel: Mapped["Reel"] = relationship(
        back_populates="reel_resources",
    )

    resource: Mapped["Resource"] = relationship(
        back_populates="reel_resources",
    )

    __table_args__ = (
        UniqueConstraint(
            "reel_id",
            "resource_id",
            name="uq_reel_resource",
        ),
    )


# ============================================================
# PROCESSING JOBS
# ============================================================

class ProcessingJob(Base):

    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    reel_id: Mapped[int] = mapped_column(
        ForeignKey(
            "reels.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    job_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    started_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    reel: Mapped["Reel"] = relationship(
        back_populates="processing_jobs",
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db() -> None:
    """
    Create all tables if they don't already exist.
    """

    Base.metadata.create_all(
        bind=engine
    )


def get_db():
    """
    Generator for FastAPI/database consumers.
    """

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    init_db()

    print(
        "Reel2Career database initialized."
    )

    print(
        f"Database: {DATABASE_FILE}"
    )

    print(
        f"Tables: {len(Base.metadata.tables)}"
    )

    for table_name in Base.metadata.tables:
        print(
            f"  - {table_name}"
        )