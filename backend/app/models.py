from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    imported_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    row_count = Column(Integer, nullable=False)

    user = relationship("User")


class RawTransaction(Base):
    __tablename__ = "raw_transactions"

    id = Column(Integer, primary_key=True, index=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=False)
    txn_date_raw = Column(String(32), nullable=False)
    amount_raw = Column(String(64), nullable=False)
    description_raw = Column(Text, nullable=False)
    balance_raw = Column(String(64), nullable=True)

    import_batch = relationship("ImportBatch")


class FctTransaction(Base):
    __tablename__ = "fct_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    txn_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    description_raw = Column(Text, nullable=False)
    merchant_key = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False, default="Unknown")
    is_income = Column(Boolean, nullable=False, default=False)
    is_movement = Column(Boolean, nullable=False, default=False)
    is_high_impact = Column(Boolean, nullable=False, default=False)
    txn_hash = Column(String(64), nullable=False)
    user_confirmed = Column(Boolean, nullable=False, default=False)

    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "txn_hash", name="uq_fct_transactions_user_hash"),
    )


class MerchantMap(Base):
    __tablename__ = "merchant_map"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    merchant_key = Column(String(255), primary_key=True)
    category = Column(String(64), nullable=False)
    source = Column(String(32), nullable=False, default="user")
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserProfile(Base):
    __tablename__ = "user_profile"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    reported_total_savings = Column(Float, nullable=True)
    bank_balance_override = Column(Float, nullable=True)
    savings_balance_override = Column(Float, nullable=True)
    investments_balance_override = Column(Float, nullable=True)
    balances_as_of = Column(Date, nullable=True)


class Goal(Base):
    __tablename__ = "goals"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    goal_amount = Column(Float, nullable=False)
    target_date = Column(Date, nullable=False)
