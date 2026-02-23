"""
Flask application for portfolio reconciliation system.
"""
import os
import logging
import tempfile
from datetime import datetime, date
from decimal import Decimal
from flask import Flask, request, jsonify
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import init_db, get_session, Account, Trade, Position
from ingestion import ingest_file
from config.logger_config import setup_logging

app = Flask(__name__)

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Database setup
DB_URL = os.environ.get("DATABASE_URL", "sqlite:///portfolio.db")

# Wipe database on startup for clean demos
if DB_URL.startswith("sqlite:///"):
  db_path = DB_URL.replace("sqlite:///", "")
  if os.path.exists(db_path):
    os.remove(db_path)
    logger.info(f"Removed existing database: {db_path}")

# Initialize fresh database
engine = init_db(DB_URL)
logger.info(f"Initialized fresh database at: {DB_URL}")


def get_db_session() -> Session:
  """Get database session for request."""
  return get_session(engine)


@app.before_request
def log_request():
  """Log incoming request details."""
  logger.info(
    f"REQUEST: {request.method} {request.path} | "
    f"Args: {dict(request.args)} | "
    f"Remote: {request.remote_addr}"
  )


@app.after_request
def log_response(response):
  """Log response details."""
  logger.info(
    f"RESPONSE: {request.method} {request.path} | "
    f"Status: {response.status_code} | "
    f"Size: {response.content_length or 0} bytes"
  )
  return response


@app.errorhandler(Exception)
def handle_error(error):
  """Global error handler."""
  logger.error(f"Unhandled error: {str(error)}", exc_info=True)
  return jsonify({"error": str(error)}), 500


@app.route("/health", methods=["GET"])
def health():
  """Health check endpoint."""
  return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.route("/ingest", methods=["POST"])
def ingest():
  """
  Ingest trade or position files via file upload.

  Expected multipart/form-data:
  - file: The file to upload (required)
  - file_format: "CSV_FORMAT1" | "PIPE_FORMAT2" | "YAML_POSITIONS" (optional, inferred from extension)
  """
  try:
    # Check if file is in the request
    if 'file' not in request.files:
      return jsonify({"error": "No file provided in request"}), 400

    uploaded_file = request.files['file']

    if uploaded_file.filename == '':
      return jsonify({"error": "Empty filename"}), 400

    # Get file format from form data or infer from filename
    file_format = request.form.get('file_format')

    if not file_format:
      # Infer format from filename
      filename = uploaded_file.filename.lower()
      if filename.endswith('.csv') and 'format1' in filename:
        file_format = 'CSV_FORMAT1'
      elif filename.endswith('.txt') or ('format2' in filename and filename.endswith('.csv')):
        file_format = 'PIPE_FORMAT2'
      elif filename.endswith('.yaml') or filename.endswith('.yml'):
        file_format = 'YAML_POSITIONS'
      else:
        return jsonify({
          "error": "Could not infer file_format from filename. Please specify explicitly.",
          "hint": "Use file_format form field: CSV_FORMAT1, PIPE_FORMAT2, or YAML_POSITIONS"
        }), 400

    session = get_db_session()
    try:
      # Save uploaded file to a temporary location
      with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix=os.path.splitext(uploaded_file.filename)[1]) as tmp_file:
        uploaded_file.save(tmp_file.name)
        tmp_path = tmp_file.name

      try:
        # Process the file
        report = ingest_file(session, tmp_path, file_format)

        # Override file_name with original uploaded filename
        report.file_name = uploaded_file.filename

        response_data = {
          "file_name": report.file_name,
          "file_format": report.file_format,
          "records_processed": report.records_processed,
          "records_valid": report.records_valid,
          "records_failed": report.records_failed,
          "success_rate": f"{report.success_rate:.2f}%",
          "new_accounts_created": report.new_accounts_created,
          "custodians_detected": report.custodians_detected,
          "errors": report.errors,
          "warnings": report.warnings,
          "status": "success" if not report.has_errors else "partial_success",
        }

        logger.info(f"Ingestion completed: {report.file_name} - {report.records_valid} records")
        return jsonify(response_data), 200 if not report.has_errors else 207

      finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
          os.unlink(tmp_path)

    finally:
      session.close()

  except Exception as e:
    logger.error(f"Ingestion failed: {str(e)}", exc_info=True)
    return jsonify({"error": str(e)}), 500


@app.route("/positions", methods=["GET"])
def get_positions():
  """
  Get positions for an account on a specific date.

  Query params:
  - account: Account ID (required)
  - date: Date in YYYY-MM-DD format (required)
  """
  try:
    account_id = request.args.get("account")
    date_str = request.args.get("date")

    if not account_id or not date_str:
      return jsonify(
        {"error": "Both 'account' and 'date' parameters are required"}
      ), 400

    try:
      query_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
      return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    session = get_db_session()
    try:
      # Get positions from bank file
      positions = (
        session.query(Position)
        .filter(
          Position.account_id == account_id,
          Position.report_date == query_date
        )
        .all()
      )

      if not positions:
        # Try to calculate from trades if no position data
        logger.warning(
          f"No position data found for {account_id} on {query_date}. "
          f"Attempting to calculate from trades."
        )
        return calculate_positions_from_trades(session, account_id, query_date)

      # Calculate cost basis from trades
      result = []
      for pos in positions:
        # Get trades for this ticker up to this date
        trades = (
          session.query(Trade)
          .filter(
            Trade.account_id == account_id,
            Trade.ticker == pos.ticker,
            Trade.trade_date <= query_date
          )
          .order_by(Trade.trade_date)
          .all()
        )

        total_cost = Decimal(0)
        total_shares = 0

        for trade in trades:
          if trade.price:
            # Use actual price from trade
            total_cost += trade.price * abs(trade.quantity)
          elif trade.market_value:
            # Use market value from trade
            total_cost += abs(trade.market_value)

          total_shares += trade.quantity

        # Calculate average cost basis
        cost_basis = total_cost / total_shares if total_shares != 0 else Decimal(0)

        result.append({
          "ticker": pos.ticker,
          "shares": pos.shares,
          "market_value": float(pos.market_value),
          "cost_basis": float(cost_basis),
          "total_cost": float(total_cost),
          "unrealized_pnl": float(pos.market_value - total_cost),
          "custodian_ref": pos.custodian_ref,
        })

      response = {
        "account_id": account_id,
        "date": date_str,
        "positions": result,
        "total_market_value": float(sum(p.market_value for p in positions)),
      }

      logger.info(f"Positions retrieved for {account_id} on {date_str}: {len(result)} positions")
      return jsonify(response), 200

    finally:
      session.close()

  except Exception as e:
    logger.error(f"Failed to retrieve positions: {str(e)}", exc_info=True)
    return jsonify({"error": str(e)}), 500


def calculate_positions_from_trades(session: Session, account_id: str, query_date: date):
  """Calculate positions from trade history when position data not available."""
  trades = (
    session.query(Trade)
    .filter(
      Trade.account_id == account_id,
      Trade.trade_date <= query_date
    )
    .all()
  )

  if not trades:
    return jsonify({
      "account_id": account_id,
      "date": query_date.strftime("%Y-%m-%d"),
      "positions": [],
      "total_market_value": 0.0,
      "note": "No trade or position data found"
    }), 404

  # Aggregate by ticker
  positions_map = {}
  for trade in trades:
    if trade.ticker not in positions_map:
      positions_map[trade.ticker] = {
        "shares": 0,
        "total_cost": Decimal(0),
      }

    positions_map[trade.ticker]["shares"] += trade.quantity

    if trade.price:
      positions_map[trade.ticker]["total_cost"] += trade.price * abs(trade.quantity)
    elif trade.market_value:
      positions_map[trade.ticker]["total_cost"] += abs(trade.market_value)

  # Build result (note: no current market value available)
  result = []
  for ticker, data in positions_map.items():
    if data["shares"] != 0: # Only include non-zero positions
      cost_basis = data["total_cost"] / data["shares"] if data["shares"] != 0 else Decimal(0)
      result.append({
        "ticker": ticker,
        "shares": data["shares"],
        "cost_basis": float(cost_basis),
        "total_cost": float(data["total_cost"]),
        "market_value": None,
        "note": "Calculated from trades; no current market value"
      })

  response = {
    "account_id": account_id,
    "date": query_date.strftime("%Y-%m-%d"),
    "positions": result,
    "note": "Calculated from trade history; no position file data available"
  }

  return jsonify(response), 200


@app.route("/compliance/concentration", methods=["GET"])
def compliance_concentration():
  """
  Check for concentration violations (>20% of account value in single position).
  Returns violations calculated from BOTH bank positions and trade positions.

  Query params:
  - date: Date in YYYY-MM-DD format (required)
  """
  try:
    date_str = request.args.get("date")

    if not date_str:
      return jsonify({"error": "'date' parameter is required"}), 400

    try:
      query_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
      return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    session = get_db_session()
    try:
      threshold = Decimal("0.20") # 20%

      # ===== CALCULATE FROM TRADES =====
      trades = (
        session.query(Trade)
        .filter(Trade.trade_date <= query_date)
        .all()
      )

      violations_from_trades = []
      if trades:
        # Group by (account, ticker) and calculate positions
        positions_map = {}
        for trade in trades:
          key = (trade.account_id, trade.ticker)
          if key not in positions_map:
            positions_map[key] = {
              'shares': 0,
              'total_value': Decimal(0)
            }

          positions_map[key]['shares'] += trade.quantity

          if trade.price:
            positions_map[key]['total_value'] += trade.price * trade.quantity
          elif trade.market_value:
            positions_map[key]['total_value'] += trade.market_value

        # Group by account and calculate totals
        account_positions = {}
        for (account_id, ticker), data in positions_map.items():
          if data['shares'] == 0:
            continue

          if account_id not in account_positions:
            account_positions[account_id] = []

          account_positions[account_id].append({
            'ticker': ticker,
            'shares': data['shares'],
            'market_value': data['total_value']
          })

        # Check violations
        for account_id, positions_list in sorted(account_positions.items()):
          # Only include POSITIVE positions in account total
          # (Short positions/negative values excluded from concentration calculation)
          total_value = sum(p['market_value'] for p in positions_list if p['market_value'] > 0)

          for pos in sorted(positions_list, key=lambda x: x['ticker']):
            # Only check concentration for positive positions
            if pos['market_value'] <= 0:
              continue

            concentration = pos['market_value'] / total_value if total_value > 0 else Decimal(0)

            if concentration > threshold:
              violations_from_trades.append({
                "account_id": account_id,
                "ticker": pos['ticker'],
                "shares": pos['shares'],
                "market_value": float(pos['market_value']),
                "account_total_value": float(total_value),
                "concentration_pct": float(concentration * 100),
                "threshold_pct": 20.0,
                "excess_pct": float((concentration - threshold) * 100),
              })

      # ===== CALCULATE FROM BANK POSITIONS =====
      bank_positions = (
        session.query(Position)
        .filter(Position.report_date == query_date)
        .all()
      )

      violations_from_bank = []
      if bank_positions:
        # Group by account
        account_positions_bank = {}
        for pos in bank_positions:
          if pos.account_id not in account_positions_bank:
            account_positions_bank[pos.account_id] = []
          account_positions_bank[pos.account_id].append(pos)

        # Check violations
        for account_id, positions_list in sorted(account_positions_bank.items()):
          # Only include POSITIVE positions in account total
          total_value = sum(p.market_value for p in positions_list if p.market_value > 0)

          for pos in sorted(positions_list, key=lambda x: x.ticker):
            # Only check concentration for positive positions
            if pos.market_value <= 0:
              continue

            concentration = pos.market_value / total_value if total_value > 0 else Decimal(0)

            if concentration > threshold:
              violations_from_bank.append({
                "account_id": account_id,
                "ticker": pos.ticker,
                "shares": pos.shares,
                "market_value": float(pos.market_value),
                "account_total_value": float(total_value),
                "concentration_pct": float(concentration * 100),
                "threshold_pct": 20.0,
                "excess_pct": float((concentration - threshold) * 100),
                "custodian_ref": pos.custodian_ref,
              })

      response = {
        "date": date_str,
        "threshold_pct": 20.0,
        "from_trades": {
          "violations_found": len(violations_from_trades),
          "violations": violations_from_trades,
          "note": "Calculated from trade history"
        },
        "from_bank": {
          "violations_found": len(violations_from_bank),
          "violations": violations_from_bank,
          "note": "From bank position file"
        }
      }

      logger.info(
        f"Compliance check for {date_str}: "
        f"{len(violations_from_trades)} violations from trades, "
        f"{len(violations_from_bank)} violations from bank"
      )
      return jsonify(response), 200

    finally:
      session.close()

  except Exception as e:
    logger.error(f"Compliance check failed: {str(e)}", exc_info=True)
    return jsonify({"error": str(e)}), 500


@app.route("/reconciliation", methods=["GET"])
def reconciliation():
  """
  Reconcile trades vs position file discrepancies.

  Query params:
  - date: Date in YYYY-MM-DD format (required)
  """
  try:
    date_str = request.args.get("date")

    if not date_str:
      return jsonify({"error": "'date' parameter is required"}), 400

    try:
      query_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
      return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    session = get_db_session()
    try:
      # Get positions from bank file
      bank_positions = (
        session.query(Position)
        .filter(Position.report_date == query_date)
        .all()
      )

      # Get trades up to this date and calculate expected positions
      trades = (
        session.query(Trade)
        .filter(Trade.trade_date <= query_date)
        .all()
      )

      # Calculate expected positions from trades
      expected_positions = {}
      for trade in trades:
        key = (trade.account_id, trade.ticker)
        if key not in expected_positions:
          expected_positions[key] = 0
        expected_positions[key] += trade.quantity

      # Build map of bank positions
      bank_positions_map = {}
      for pos in bank_positions:
        key = (pos.account_id, pos.ticker)
        bank_positions_map[key] = pos.shares

      # Find discrepancies
      discrepancies = []

      # Check all expected positions
      all_keys = set(expected_positions.keys()) | set(bank_positions_map.keys())

      for key in sorted(all_keys): # Sort by (account_id, ticker)
        account_id, ticker = key
        expected = expected_positions.get(key, 0)
        actual = bank_positions_map.get(key, 0)

        if expected != actual:
          discrepancies.append({
            "account_id": account_id,
            "ticker": ticker,
            "expected_shares": expected,
            "actual_shares": actual,
            "difference": actual - expected,
            "status": "missing_in_bank" if actual == 0 else
                 "missing_in_trades" if expected == 0 else
                 "quantity_mismatch"
          })

      response = {
        "date": date_str,
        "total_positions_in_bank": len(bank_positions),
        "total_positions_from_trades": len(expected_positions),
        "discrepancies_found": len(discrepancies),
        "discrepancies": discrepancies,
      }

      logger.info(
        f"Reconciliation for {date_str}: {len(discrepancies)} discrepancies found"
      )
      return jsonify(response), 200

    finally:
      session.close()

  except Exception as e:
    logger.error(f"Reconciliation failed: {str(e)}", exc_info=True)
    return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
  app.run(debug=True, host="0.0.0.0", port=5000)
