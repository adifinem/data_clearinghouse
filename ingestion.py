"""
Data ingestion logic with quality checks.
"""
import csv
import yaml
import logging
from pathlib import Path
from typing import List, Tuple
from decimal import Decimal
from sqlalchemy.orm import Session

from models import Account, Trade, Position
from validators import (
  TradeFormat1,
  TradeFormat2,
  BankPositionFile,
  DataQualityReport,
)

logger = logging.getLogger(__name__)


def extract_custodian_name(custodian_ref: str) -> str:
  """
  Extract custodian name from custodian reference.
  CUST_A_12345 -> CUSTODIAN_A
  """
  if not custodian_ref:
    return None
  parts = custodian_ref.split("_")
  if len(parts) >= 2:
    return f"CUSTODIAN_{parts[1]}"
  return None


def ensure_account_exists(session: Session, account_id: str, custodian: str = None) -> Account:
  """
  Ensure account exists in database, create if not.
  Update custodian if provided and not already set.
  """
  account = session.query(Account).filter_by(account_id=account_id).first()

  if not account:
    account = Account(account_id=account_id, custodian_name=custodian)
    session.add(account)
    logger.info(f"Created new account: {account_id} with custodian: {custodian}")
    return account

  # Update custodian if provided and not already set
  if custodian and not account.custodian_name:
    account.custodian_name = custodian
    logger.info(f"Updated account {account_id} with custodian: {custodian}")

  return account


def ingest_trade_format1(
  session: Session, file_path: str
) -> DataQualityReport:
  """
  Ingest CSV trade file (Format 1).
  """
  report = DataQualityReport(
    file_name=Path(file_path).name,
    file_format="CSV_FORMAT1"
  )

  try:
    with open(file_path, "r") as f:
      reader = csv.DictReader(f)
      for row_num, row in enumerate(reader, start=2): # Start at 2 (header is row 1)
        report.records_processed += 1
        try:
          # Validate with Pydantic
          validated = TradeFormat1(**row)

          # Ensure account exists
          account = ensure_account_exists(session, validated.account_id)
          if not session.query(Account).filter_by(account_id=validated.account_id).first():
            report.new_accounts_created += 1

          # Calculate quantity (negative for SELL)
          quantity = validated.quantity
          if validated.trade_type.value == "SELL":
            quantity = -quantity

          # Calculate market value
          market_value = validated.price * abs(quantity)

          # Create trade record
          trade = Trade(
            trade_date=validated.trade_date,
            account_id=validated.account_id,
            ticker=validated.ticker,
            quantity=quantity,
            price=validated.price,
            trade_type=validated.trade_type.value,
            settlement_date=validated.settlement_date,
            market_value=market_value,
            file_format=report.file_format,
            source_file=report.file_name,
          )
          session.add(trade)
          report.records_valid += 1

        except Exception as e:
          report.records_failed += 1
          error_msg = f"Row {row_num}: {str(e)}"
          report.errors.append(error_msg)
          logger.error(f"Failed to process row {row_num} in {file_path}: {e}")

    session.commit()
    logger.info(
      f"Ingested {report.records_valid}/{report.records_processed} "
      f"records from {report.file_name}"
    )

  except Exception as e:
    session.rollback()
    report.errors.append(f"File processing error: {str(e)}")
    logger.error(f"Failed to process file {file_path}: {e}")

  return report


def ingest_trade_format2(
  session: Session, file_path: str
) -> DataQualityReport:
  """
  Ingest pipe-delimited trade file (Format 2).
  """
  report = DataQualityReport(
    file_name=Path(file_path).name,
    file_format="PIPE_FORMAT2"
  )

  custodians = set()

  try:
    with open(file_path, "r") as f:
      reader = csv.DictReader(f, delimiter="|")
      for row_num, row in enumerate(reader, start=2):
        report.records_processed += 1
        try:
          # Validate with Pydantic
          validated = TradeFormat2(**row)

          # Track custodians
          custodians.add(validated.source_system)

          # Ensure account exists with custodian info
          account = ensure_account_exists(
            session, validated.account_id, validated.source_system
          )
          if not session.query(Account).filter_by(account_id=validated.account_id).first():
            report.new_accounts_created += 1

          # Create trade record
          trade = Trade(
            trade_date=validated.report_date,
            account_id=validated.account_id,
            ticker=validated.ticker,
            quantity=validated.shares,
            price=validated.derived_price,
            market_value=validated.market_value,
            source_system=validated.source_system,
            file_format=report.file_format,
            source_file=report.file_name,
          )
          session.add(trade)
          report.records_valid += 1

        except Exception as e:
          report.records_failed += 1
          error_msg = f"Row {row_num}: {str(e)}"
          report.errors.append(error_msg)
          logger.error(f"Failed to process row {row_num} in {file_path}: {e}")

    session.commit()
    report.custodians_detected = sorted(list(custodians))
    logger.info(
      f"Ingested {report.records_valid}/{report.records_processed} "
      f"records from {report.file_name}. Custodians: {report.custodians_detected}"
    )

  except Exception as e:
    session.rollback()
    report.errors.append(f"File processing error: {str(e)}")
    logger.error(f"Failed to process file {file_path}: {e}")

  return report


def ingest_bank_positions(
  session: Session, file_path: str
) -> DataQualityReport:
  """
  Ingest YAML bank position file.
  """
  report = DataQualityReport(
    file_name=Path(file_path).name,
    file_format="YAML_POSITIONS"
  )

  custodians = set()

  try:
    with open(file_path, "r") as f:
      data = yaml.safe_load(f)

    # Validate with Pydantic
    validated_file = BankPositionFile(**data)
    report_date = validated_file.report_date

    for position_data in validated_file.positions:
      report.records_processed += 1
      try:
        # Extract custodian from reference
        custodian = extract_custodian_name(position_data.custodian_ref)
        if custodian:
          custodians.add(custodian)

        # Ensure account exists with custodian info
        account = ensure_account_exists(
          session, position_data.account_id, custodian
        )
        if not session.query(Account).filter_by(account_id=position_data.account_id).first():
          report.new_accounts_created += 1

        # Create position record
        position = Position(
          report_date=report_date,
          account_id=position_data.account_id,
          ticker=position_data.ticker,
          shares=position_data.shares,
          market_value=position_data.market_value,
          custodian_ref=position_data.custodian_ref,
          source_file=report.file_name,
        )
        session.add(position)
        report.records_valid += 1

      except Exception as e:
        report.records_failed += 1
        error_msg = f"Position record: {str(e)}"
        report.errors.append(error_msg)
        logger.error(f"Failed to process position in {file_path}: {e}")

    session.commit()
    report.custodians_detected = sorted(list(custodians))
    logger.info(
      f"Ingested {report.records_valid}/{report.records_processed} "
      f"positions from {report.file_name}. Custodians: {report.custodians_detected}"
    )

  except Exception as e:
    session.rollback()
    report.errors.append(f"File processing error: {str(e)}")
    logger.error(f"Failed to process file {file_path}: {e}")

  return report


def ingest_file(session: Session, file_path: str, file_format: str) -> DataQualityReport:
  """
  Main ingestion entry point. Routes to appropriate handler based on format.
  """
  logger.info(f"Starting ingestion of {file_path} as format: {file_format}")

  if file_format == "CSV_FORMAT1":
    return ingest_trade_format1(session, file_path)
  elif file_format == "PIPE_FORMAT2":
    return ingest_trade_format2(session, file_path)
  elif file_format == "YAML_POSITIONS":
    return ingest_bank_positions(session, file_path)
  else:
    report = DataQualityReport(
      file_name=Path(file_path).name,
      file_format=file_format
    )
    report.errors.append(f"Unknown file format: {file_format}")
    return report
