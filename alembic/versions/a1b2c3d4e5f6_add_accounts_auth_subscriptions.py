"""Add parlayvu.ai customer login + subscription tables.

Adds:
- accounts          (paying parlayvu.ai customers)
- magic_links       (single-use passwordless sign-in tokens, stored hashed)
- login_sessions    (browser sessions, stored hashed)
- subscriptions     (mirror of Stripe subscriptions, synced by webhook)

Revision ID: a1b2c3d4e5f6
Revises: 737d4026c0ca
Create Date: 2026-06-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "737d4026c0ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("stripe_customer_id", sa.String(128), nullable=True),
        sa.Column("client_id", sa.String(64), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_accounts_email", "accounts", ["email"], unique=True)
    op.create_index(
        "ix_accounts_stripe_customer_id", "accounts", ["stripe_customer_id"], unique=True
    )
    op.create_index("ix_accounts_client_id", "accounts", ["client_id"])

    op.create_table(
        "magic_links",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_magic_links_account_id", "magic_links", ["account_id"])
    op.create_index("ix_magic_links_token_hash", "magic_links", ["token_hash"], unique=True)

    op.create_table(
        "login_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_login_sessions_account_id", "login_sessions", ["account_id"])
    op.create_index(
        "ix_login_sessions_token_hash", "login_sessions", ["token_hash"], unique=True
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="incomplete"),
        sa.Column("price_id", sa.String(128), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscriptions_account_id", "subscriptions", ["account_id"])
    op.create_index(
        "ix_subscriptions_stripe_subscription_id",
        "subscriptions",
        ["stripe_subscription_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("login_sessions")
    op.drop_table("magic_links")
    op.drop_table("accounts")
