from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import uuid

class Base(DeclarativeBase):
    pass

class Show(Base):
    __tablename__ = "shows"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    price_paise: Mapped[int] = mapped_column(BigInteger)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=4)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Seat(Base):
    __tablename__ = "seats"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    show_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shows.id", ondelete="CASCADE"))
    seat_number: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="available")
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("show_id", "seat_number"), CheckConstraint("status IN ('available','held','confirmed')"))

class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    show_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shows.id", ondelete="RESTRICT"))
    user_id: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(Text)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("show_id", "user_id", "idempotency_key"),)

class ReservationSeat(Base):
    __tablename__ = "reservation_seats"
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reservations.id", ondelete="CASCADE"), primary_key=True)
    seat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seats.id", ondelete="RESTRICT"), primary_key=True)
