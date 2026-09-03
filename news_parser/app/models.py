from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class PeriodEnum(str, Enum):
    day = "day"
    week = "week"
    month = "month"


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("channel_username", "message_id", name="uq_channel_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_username: Mapped[str] = mapped_column(String(255), index=True)
    channel_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    message_id: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    topic_links: Mapped[list["TopicPost"]] = relationship(back_populates="post")


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("period", "slug", name="uq_period_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    slug: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        insert_default=_utcnow,
    )

    post_links: Mapped[list["TopicPost"]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class TopicPost(Base):
    __tablename__ = "topic_posts"
    __table_args__ = (UniqueConstraint("topic_id", "post_id", name="uq_topic_post"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))

    topic: Mapped["Topic"] = relationship(back_populates="post_links")
    post: Mapped["Post"] = relationship(back_populates="topic_links")
