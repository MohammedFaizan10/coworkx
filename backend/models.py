"""
CoWorkX — Database Models (SQLAlchemy)
All 5 tables: users, machines, tasks, task_steps, transactions
"""

import uuid
import enum
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text,
    Enum, Numeric, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.sql import func
from database import Base


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    user  = "user"
    owner = "owner"
    both  = "both"

class MachineStatus(str, enum.Enum):
    online  = "online"
    busy    = "busy"
    offline = "offline"

class TaskStatus(str, enum.Enum):
    queued    = "queued"
    running   = "running"
    completed = "completed"
    failed    = "failed"
    cancelled = "cancelled"

class TaskType(str, enum.Enum):
    browsing  = "browsing"
    coding    = "coding"
    file      = "file"
    research  = "research"
    multi     = "multi"

class TxType(str, enum.Enum):
    task_payment  = "task_payment"
    owner_reward  = "owner_reward"
    top_up        = "top_up"
    refund        = "refund"
    platform_fee  = "platform_fee"


# ─────────────────────────────────────────────────────────────────────────────
# TABLE 1: users
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email           = Column(String(255), unique=True, nullable=True)
    password_hash   = Column(String(255), nullable=True)
    wallet_address  = Column(String(42), unique=True, nullable=True)
    display_name    = Column(String(100), nullable=False)
    credit_balance  = Column(Numeric(18, 8), default=100.0)   # 100 free credits on signup
    total_earned    = Column(Numeric(18, 8), default=0)
    total_spent     = Column(Numeric(18, 8), default=0)
    role            = Column(Enum(UserRole), default=UserRole.user)
    is_verified     = Column(Boolean, default=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    last_active     = Column(DateTime(timezone=True), onupdate=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# TABLE 2: machines
# ─────────────────────────────────────────────────────────────────────────────

class Machine(Base):
    __tablename__ = "machines"

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id              = Column(UUID(as_uuid=True), nullable=False)              # FK → users.id
    display_name          = Column(String(100), nullable=False)
    os                    = Column(String(50), nullable=False)                      # windows/macos/linux
    cpu_model             = Column(String(100), nullable=False)
    cpu_cores             = Column(Integer, nullable=False)
    ram_gb                = Column(Integer, nullable=False)
    gpu_model             = Column(String(100), nullable=True)
    gpu_vram_gb           = Column(Integer, nullable=True)
    storage_gb            = Column(Integer, nullable=False)
    installed_software    = Column(ARRAY(Text), default=[])
    supported_tasks       = Column(ARRAY(Text), default=[])
    price_per_hour        = Column(Numeric(10, 4), default=1.0)
    latitude              = Column(Numeric(9, 6), nullable=False)
    longitude             = Column(Numeric(9, 6), nullable=False)
    status                = Column(Enum(MachineStatus), default=MachineStatus.offline)
    cpu_usage_pct         = Column(Integer, default=0)
    ram_usage_pct         = Column(Integer, default=0)
    last_heartbeat        = Column(DateTime(timezone=True), nullable=True)
    total_tasks_completed = Column(Integer, default=0)
    rating                = Column(Numeric(3, 2), default=5.0)
    daemon_version        = Column(String(20), default="0.0.1")
    registered_at         = Column(DateTime(timezone=True), server_default=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# TABLE 3: tasks
# ─────────────────────────────────────────────────────────────────────────────

class Task(Base):
    __tablename__ = "tasks"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id            = Column(UUID(as_uuid=True), nullable=False)
    machine_id         = Column(UUID(as_uuid=True), nullable=False)
    task_description   = Column(Text, nullable=False)
    task_type          = Column(String(50), default="browsing")
    model_used         = Column(String(50), default="claude-sonnet-4")
    status             = Column(Enum(TaskStatus), default=TaskStatus.queued)
    credits_charged    = Column(Numeric(18, 8), default=0)
    credits_earned     = Column(Numeric(18, 8), default=0)
    started_at         = Column(DateTime(timezone=True), nullable=True)
    completed_at       = Column(DateTime(timezone=True), nullable=True)
    duration_seconds   = Column(Integer, nullable=True)
    output_url         = Column(Text, nullable=True)
    blockchain_tx_hash = Column(String(66), nullable=True)
    proof_ipfs_hash    = Column(String(59), nullable=True)
    error_message      = Column(Text, nullable=True)
    steps_count        = Column(Integer, nullable=True)
    swarm_size         = Column(Integer, default=1)   # 1 = single, >1 = swarm
    created_at         = Column(DateTime(timezone=True), server_default=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# TABLE 4: task_steps
# ─────────────────────────────────────────────────────────────────────────────

class TaskStep(Base):
    __tablename__ = "task_steps"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id         = Column(UUID(as_uuid=True), nullable=False)
    step_number     = Column(Integer, nullable=False)
    action_type     = Column(String(50), nullable=False)   # navigate/click/type/screenshot/etc.
    action_params   = Column(JSONB, default={})             # {url:'...', selector:'...'}
    screenshot_hash = Column(String(64), nullable=True)    # SHA-256 before action
    result_hash     = Column(String(64), nullable=True)    # SHA-256 after action
    reasoning       = Column(Text, nullable=True)          # Claude's reasoning
    executed_at     = Column(DateTime(timezone=True), server_default=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# TABLE 5: transactions
# ─────────────────────────────────────────────────────────────────────────────

class Transaction(Base):
    __tablename__ = "transactions"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_user_id       = Column(UUID(as_uuid=True), nullable=True)
    to_user_id         = Column(UUID(as_uuid=True), nullable=True)
    task_id            = Column(UUID(as_uuid=True), nullable=True)
    amount             = Column(Numeric(18, 8), nullable=False)
    tx_type            = Column(Enum(TxType), nullable=False)
    blockchain_tx_hash = Column(String(66), nullable=True)
    created_at         = Column(DateTime(timezone=True), server_default=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# TABLE 6: wallets   (Day 6 — mock token economy)
# ─────────────────────────────────────────────────────────────────────────────

class Wallet(Base):
    __tablename__ = "wallets"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id   = Column(UUID(as_uuid=True), unique=True, nullable=False)   # user or machine owner
    balance    = Column(Numeric(18, 8), default=100.0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ─────────────────────────────────────────────────────────────────────────────
# TABLE 7: wallet_transactions   (Day 6 — mock blockchain ledger)
# A separate table from `transactions` so it auto-creates cleanly without
# touching the existing schema. Stores a fake-but-realistic tx_hash.
# ─────────────────────────────────────────────────────────────────────────────

class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_owner  = Column(UUID(as_uuid=True), nullable=True)
    to_owner    = Column(UUID(as_uuid=True), nullable=True)
    task_id     = Column(UUID(as_uuid=True), nullable=True)
    amount      = Column(Numeric(18, 8), nullable=False)
    type        = Column(String(20), nullable=False)   # lock | release | refund | reward
    tx_hash     = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
