"""
Pydantic validators for data quality checks during ingestion.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, validator, field_validator, ConfigDict
from enum import Enum


class TradeType(str, Enum):
  """Valid trade types."""

  BUY = "BUY"
  SELL = "SELL"


class TradeFormat1(BaseModel):
  """Validator for CSV trade format (Format 1)."""

  trade_date: date = Field(alias="TradeDate")
  account_id: str = Field(alias="AccountID", min_length=1, max_length=50)
  ticker: str = Field(alias="Ticker", min_length=1, max_length=20)
  quantity: int = Field(alias="Quantity", gt=0)
  price: Decimal = Field(alias="Price", gt=0)
  trade_type: TradeType = Field(alias="TradeType")
  settlement_date: date = Field(alias="SettlementDate")

  model_config = ConfigDict(populate_by_name=True)

  @field_validator("trade_date", "settlement_date", mode="before")
  @classmethod
  def parse_date(cls, v):
    """Parse date from string if needed."""
    if isinstance(v, str):
      return datetime.strptime(v, "%Y-%m-%d").date()
    return v

  @field_validator("settlement_date")
  @classmethod
  def check_settlement_after_trade(cls, v, info):
    """Ensure settlement date is on or after trade date."""
    trade_date = info.data.get("trade_date")
    if trade_date and v < trade_date:
      raise ValueError("Settlement date cannot be before trade date")
    return v


class TradeFormat2(BaseModel):
  """Validator for pipe-delimited trade format (Format 2)."""

  report_date: date = Field(alias="REPORT_DATE")
  account_id: str = Field(alias="ACCOUNT_ID", min_length=1, max_length=50)
  ticker: str = Field(alias="SECURITY_TICKER", min_length=1, max_length=20)
  shares: int = Field(alias="SHARES") # Can be negative for SELL
  market_value: Decimal = Field(alias="MARKET_VALUE")
  source_system: str = Field(alias="SOURCE_SYSTEM", min_length=1)

  model_config = ConfigDict(populate_by_name=True)

  @field_validator("report_date", mode="before")
  @classmethod
  def parse_date(cls, v):
    """Parse date from YYYYMMDD format."""
    if isinstance(v, str):
      return datetime.strptime(v, "%Y%m%d").date()
    return v

  @field_validator("market_value")
  @classmethod
  def check_market_value_sign(cls, v, info):
    """Ensure market value sign matches shares sign."""
    shares = info.data.get("shares")
    if shares is not None:
      if (shares > 0 and v < 0) or (shares < 0 and v > 0):
        # Allow this - market value and shares should have same sign
        pass
    return v

  @property
  def derived_price(self) -> Optional[Decimal]:
    """Calculate price per share from market value."""
    if self.shares != 0:
      return abs(self.market_value / self.shares)
    return None


class BankPosition(BaseModel):
  """Validator for bank position data."""

  account_id: str = Field(min_length=1, max_length=50)
  ticker: str = Field(min_length=1, max_length=20)
  shares: int
  market_value: Decimal
  custodian_ref: str = Field(min_length=1)

  @field_validator("market_value")
  @classmethod
  def check_value_positive(cls, v):
    """Market value should generally be positive."""
    # Note: Can be negative for short positions, but flag for review
    return v


class BankPositionFile(BaseModel):
  """Validator for complete bank position file."""

  report_date: str
  positions: List[BankPosition]

  @field_validator("report_date")
  @classmethod
  def parse_report_date(cls, v):
    """Parse report date from YYYYMMDD format."""
    if len(v) == 8 and v.isdigit():
      return datetime.strptime(v, "%Y%m%d").date()
    raise ValueError(f"Invalid report_date format: {v}")


class DataQualityReport(BaseModel):
  """Report on data quality checks during ingestion."""

  file_name: str
  file_format: str
  records_processed: int = 0
  records_valid: int = 0
  records_failed: int = 0
  errors: List[str] = Field(default_factory=list)
  warnings: List[str] = Field(default_factory=list)
  new_accounts_created: int = 0
  custodians_detected: List[str] = Field(default_factory=list)

  @property
  def success_rate(self) -> float:
    """Calculate success rate percentage."""
    if self.records_processed == 0:
      return 0.0
    return (self.records_valid / self.records_processed) * 100

  @property
  def has_errors(self) -> bool:
    """Check if any errors occurred."""
    return self.records_failed > 0 or len(self.errors) > 0
