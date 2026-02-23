"""
SQLAlchemy database models for portfolio reconciliation system.
"""
from datetime import datetime, date
from sqlalchemy import (
  create_engine,
  Column,
  Integer,
  String,
  Numeric,
  Date,
  DateTime,
  ForeignKey,
  Index,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Account(Base):
  """Account master data with custodian mapping."""

  __tablename__ = "accounts"

  account_id = Column(String(50), primary_key=True)
  custodian_name = Column(String(100), nullable=True)
  created_at = Column(DateTime, default=lambda: datetime.now(), nullable=False)

  # Relationships
  trades = relationship("Trade", back_populates="account")
  positions = relationship("Position", back_populates="account")

  def __repr__(self):
    return f"<Account(account_id='{self.account_id}', custodian='{self.custodian_name}')>"


class Trade(Base):
  """Unified trade table supporting multiple file formats."""

  __tablename__ = "trades"

  id = Column(Integer, primary_key=True, autoincrement=True)
  trade_date = Column(Date, nullable=False)
  account_id = Column(String(50), ForeignKey("accounts.account_id"), nullable=False)
  ticker = Column(String(20), nullable=False)
  quantity = Column(Integer, nullable=False) # Positive for BUY, negative for SELL

  # Format 1 fields (CSV)
  price = Column(Numeric(12, 2), nullable=True)
  trade_type = Column(String(10), nullable=True) # BUY, SELL
  settlement_date = Column(Date, nullable=True)

  # Format 2 fields (pipe-delimited)
  market_value = Column(Numeric(15, 2), nullable=True)
  source_system = Column(String(50), nullable=True) # CUSTODIAN_A, etc.

  # Metadata
  file_format = Column(String(20), nullable=False) # 'CSV_FORMAT1', 'PIPE_FORMAT2'
  source_file = Column(String(255), nullable=True)
  created_at = Column(DateTime, default=lambda: datetime.now(), nullable=False)

  # Relationship
  account = relationship("Account", back_populates="trades")

  # Indexes for common queries
  __table_args__ = (
    Index("idx_trade_date_account", "trade_date", "account_id"),
    Index("idx_trade_date_ticker", "trade_date", "ticker"),
  )

  def __repr__(self):
    return (
      f"<Trade(date={self.trade_date}, account={self.account_id}, "
      f"ticker={self.ticker}, qty={self.quantity})>"
    )


class Position(Base):
  """Bank/broker position snapshots."""

  __tablename__ = "positions"

  id = Column(Integer, primary_key=True, autoincrement=True)
  report_date = Column(Date, nullable=False)
  account_id = Column(String(50), ForeignKey("accounts.account_id"), nullable=False)
  ticker = Column(String(20), nullable=False)
  shares = Column(Integer, nullable=False)
  market_value = Column(Numeric(15, 2), nullable=False)
  custodian_ref = Column(String(100), nullable=True) # CUST_A_12345, etc.

  # Metadata
  source_file = Column(String(255), nullable=True)
  created_at = Column(DateTime, default=lambda: datetime.now(), nullable=False)

  # Relationship
  account = relationship("Account", back_populates="positions")

  # Indexes
  __table_args__ = (
    Index("idx_position_date_account", "report_date", "account_id"),
    Index("idx_position_date_ticker", "report_date", "ticker"),
  )

  def __repr__(self):
    return (
      f"<Position(date={self.report_date}, account={self.account_id}, "
      f"ticker={self.ticker}, shares={self.shares})>"
    )


# Database initialization
def init_db(db_url="sqlite:///portfolio.db"):
  """Initialize database and create all tables."""
  engine = create_engine(db_url, echo=False)
  Base.metadata.create_all(engine)
  return engine


def get_session(engine):
  """Get database session."""
  Session = sessionmaker(bind=engine)
  return Session()
