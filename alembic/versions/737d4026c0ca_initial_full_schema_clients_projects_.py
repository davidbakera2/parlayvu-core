"""Initial full schema for ParlayVU Core.

Includes all current tables:
- clients
- projects
- source_assets
- generated_outputs
- approvals
- agent_events
- teams_channel_bindings
- conversation_turns (Track 5 conversation memory)

This migration was written by hand because the initial autogenerate ran
without a live DATABASE_URL. It matches the SQLAlchemy 2.0 models exactly
(including TimestampMixin and the intentional lack of FKs on conversation_turns).

Revision ID: 737d4026c0ca
Revises: 
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '737d4026c0ca'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the complete initial ParlayVU schema."""
    # clients
    op.create_table(
        'clients',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('brand_voice_summary', sa.Text(), nullable=True),
        sa.Column('disclosure_rules', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('channel_preferences', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # projects
    op.create_table(
        'projects',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('client_id', sa.String(64), sa.ForeignKey('clients.id'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('approval_policy', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # source_assets
    op.create_table(
        'source_assets',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('asset_type', sa.String(80), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('uri', sa.Text(), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # generated_outputs
    op.create_table(
        'generated_outputs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('source_asset_id', sa.String(64), sa.ForeignKey('source_assets.id'), nullable=True, index=True),
        sa.Column('agent_name', sa.String(80), nullable=False),
        sa.Column('output_type', sa.String(80), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('uri', sa.Text(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # approvals
    op.create_table(
        'approvals',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('generated_output_id', sa.String(64), sa.ForeignKey('generated_outputs.id'), nullable=True, index=True),
        sa.Column('requested_by_agent', sa.String(80), nullable=False),
        sa.Column('approver', sa.String(255), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('decision_notes', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # agent_events (audit + memory)
    op.create_table(
        'agent_events',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('projects.id'), nullable=True, index=True),
        sa.Column('client_id', sa.String(64), sa.ForeignKey('clients.id'), nullable=True, index=True),
        sa.Column('agent_name', sa.String(80), nullable=False),
        sa.Column('event_type', sa.String(80), nullable=False),
        sa.Column('channel', sa.String(80), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # teams_channel_bindings
    op.create_table(
        'teams_channel_bindings',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('team_id', sa.String(255), nullable=False, index=True),
        sa.Column('channel_id', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('channel_name', sa.String(255), nullable=True),
        sa.Column('client_id', sa.String(64), sa.ForeignKey('clients.id'), nullable=False, index=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # conversation_turns (Track 5 - conversation memory for Teams / future surfaces)
    # Deliberately no FKs to clients/projects so memory can never be blocked by missing parent rows.
    op.create_table(
        'conversation_turns',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('conversation_id', sa.String(255), nullable=False, index=True),
        sa.Column('client_id', sa.String(64), nullable=True, index=True),
        sa.Column('surface', sa.String(32), nullable=False, server_default='teams_chat'),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Helpful composite index for the common lookup pattern (client + conversation + time)
    op.create_index(
        'ix_conversation_turns_client_conv_created',
        'conversation_turns',
        ['client_id', 'conversation_id', 'created_at'],
    )


def downgrade() -> None:
    """Drop the complete initial ParlayVU schema (reverse order of FK dependencies)."""
    op.drop_index('ix_conversation_turns_client_conv_created', table_name='conversation_turns')
    op.drop_table('conversation_turns')
    op.drop_table('teams_channel_bindings')
    op.drop_table('agent_events')
    op.drop_table('approvals')
    op.drop_table('generated_outputs')
    op.drop_table('source_assets')
    op.drop_table('projects')
    op.drop_table('clients')
