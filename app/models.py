from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    brand_voice_summary: Mapped[str | None] = mapped_column(Text)
    disclosure_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    channel_preferences: Mapped[dict] = mapped_column(JSON, default=dict)

    projects: Mapped[list["Project"]] = relationship(back_populates="client", cascade="all, delete-orphan")


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    objective: Mapped[str | None] = mapped_column(Text)
    approval_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    client: Mapped[Client] = relationship(back_populates="projects")
    source_assets: Mapped[list["SourceAsset"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    generated_outputs: Mapped[list["GeneratedOutput"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    agent_events: Mapped[list["AgentEvent"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    teams_channel_bindings: Mapped[list["TeamsChannelBinding"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class SourceAsset(Base, TimestampMixin):
    __tablename__ = "source_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    uri: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="source_assets")


class GeneratedOutput(Base, TimestampMixin):
    __tablename__ = "generated_outputs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    source_asset_id: Mapped[str | None] = mapped_column(ForeignKey("source_assets.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    output_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    uri: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="generated_outputs")
    source_asset: Mapped[SourceAsset | None] = relationship()


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    generated_output_id: Mapped[str | None] = mapped_column(ForeignKey("generated_outputs.id"), index=True)
    requested_by_agent: Mapped[str] = mapped_column(String(80), nullable=False)
    approver: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    decision_notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="approvals")
    generated_output: Mapped[GeneratedOutput | None] = relationship()


class AgentEvent(Base, TimestampMixin):
    __tablename__ = "agent_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(80))
    summary: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project | None] = relationship(back_populates="agent_events")
    client: Mapped[Client | None] = relationship()


class TeamsChannelBinding(Base, TimestampMixin):
    __tablename__ = "teams_channel_bindings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    channel_name: Mapped[str | None] = mapped_column(String(255))
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    client: Mapped[Client] = relationship()
    project: Mapped[Project] = relationship(back_populates="teams_channel_bindings")


class ConversationTurn(Base, TimestampMixin):
    """One user-or-assistant turn in a Teams (or future-surface) conversation.

    Append-only, denormalized for fast replay. Not a foreign-key relationship
    to clients/projects on purpose — conversation memory should never fail
    because a parent row is missing. Scope-by-conversation_id is the primary
    lookup; client_id is stored alongside so we can scope cross-checks and
    enforce isolation between clients sharing a Teams tenant.

    Replay defaults: 20 turns, 72h, 60K chars (see load_conversation_history
    in app/project_memory.py). Reset clears all rows for a (conversation_id,
    client_id) pair.
    """

    __tablename__ = "conversation_turns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(String(64), index=True)
    surface: Mapped[str] = mapped_column(String(32), nullable=False, default="teams_chat")
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
