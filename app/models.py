import time
import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def identifier():
    return str(uuid.uuid4())


def now():
    return int(time.time())


class Workspace(Base):
    __tablename__ = 'workspaces'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(80))


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (CheckConstraint("role IN ('owner', 'editor', 'viewer')", name='valid_role'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(10), default='owner')
    is_email_verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[int] = mapped_column(default=now)


class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    expires_at: Mapped[int] = mapped_column(index=True)
    created_at: Mapped[int] = mapped_column(default=now)


class ActionToken(Base):
    __tablename__ = 'action_tokens'
    __table_args__ = (Index('ix_action_tokens_user_purpose', 'user_id', 'purpose'),)
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    purpose: Mapped[str] = mapped_column(String(24))
    expires_at: Mapped[int] = mapped_column(index=True)
    created_at: Mapped[int] = mapped_column(default=now)


class Product(Base):
    __tablename__ = 'products'
    __table_args__ = (
        UniqueConstraint('workspace_id', 'sku', name='unique_workspace_sku'),
        CheckConstraint('quantity >= 0 AND price_cents >= 0 AND reorder_point >= 0', name='nonnegative_inventory'),
        Index('ix_products_workspace_updated', 'workspace_id', 'updated_at'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'))
    name: Mapped[str] = mapped_column(String(120))
    sku: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text, default='')
    quantity: Mapped[int] = mapped_column(default=0)
    price_cents: Mapped[int] = mapped_column(default=0)
    reorder_point: Mapped[int] = mapped_column(default=10)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[int] = mapped_column(default=now)
    updated_at: Mapped[int] = mapped_column(default=now)


class Audit(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'), index=True)
    actor_name: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    target: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[int] = mapped_column(default=now, index=True)


class RateBucket(Base):
    __tablename__ = 'rate_buckets'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(default=1)
    expires_at: Mapped[int] = mapped_column(index=True)
