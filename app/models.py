from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    audit_logs = relationship("AuditLog", back_populates="user")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    address = Column(String, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    status = Column(String, nullable=False)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    customer = relationship("Customer")

    total_amount_kop = Column(Integer, nullable=False)
    currency = Column(String, default="RUB", nullable=False)
    comment = Column(String, nullable=True)

    payments = relationship("Payment", back_populates="order")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(String, unique=True, nullable=False, index=True)

    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    order = relationship("Order", back_populates="payments")

    payment_method = Column(String, nullable=False)
    amount_kop = Column(Integer, nullable=False)
    currency = Column(String, default="RUB", nullable=False)
    status = Column(String, nullable=False)

    created_at = Column(DateTime, nullable=False)
    paid_at = Column(DateTime, nullable=True)

    card_last4 = Column(String, nullable=True)
    card_masked = Column(String, nullable=True)

    fee_kop = Column(Integer, default=0, nullable=False)

    refunds = relationship("Refund", back_populates="payment")


class Refund(Base):
    __tablename__ = "refunds"

    id = Column(Integer, primary_key=True, index=True)
    refund_id = Column(String, unique=True, nullable=False, index=True)

    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    payment = relationship("Payment", back_populates="refunds")

    created_at = Column(DateTime, nullable=False)
    amount_kop = Column(Integer, nullable=False)
    refund_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    reason = Column(String, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="audit_logs")

    action = Column(String, nullable=False)
    details = Column(String, nullable=True)