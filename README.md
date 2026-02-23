# Portfolio Data Clearinghouse

A portfolio data reconciliation system that ingests trade and position data from multiple sources, reconciles discrepancies, calculates portfolio metrics, and detects compliance violations.

## Quick Start

```bash
# Run everything with the provided script
./run.sh
```

Manually run different parts:
```bash
# Activate virtual environment
source venv/bin/activate
# Start flask server
python app.py

# Run the demo in different terminal (requires Flask app to be running)
python demo.py

# Or run unit tests
python -m pytest tests/ -v
```

## Overview

This system:
- Ingests trade data from 2 different file formats (CSV and pipe-delimited)
- Ingests bank position data from YAML files
- Normalizes all data into a unified relational database schema
- Provides REST API endpoints for querying positions, checking compliance, and reconciling data
- Validates all data with Pydantic schemas
- Logs all operations with configurable log levels and automatic file rotation
- **Automatically wipes database on startup** for clean demos (prevents duplicate data)

## API Endpoints

### Health Check
```
GET /health
```
Returns API health status and timestamp.

### Data Ingestion
```
POST /ingest
Content-Type: multipart/form-data

Form fields:
  - file: (file upload, required)
  - file_format: CSV_FORMAT1 | PIPE_FORMAT2 | YAML_POSITIONS (optional, auto-detected)
```

**Example using curl:**
```bash
curl -X POST http://localhost:5000/ingest \
  -F "file=@trades_format1.csv" \
  -F "file_format=CSV_FORMAT1"
```

**Example using Python:**
```python
with open("trades_format1.csv", "rb") as f:
    files = {"file": ("trades_format1.csv", f)}
    data = {"file_format": "CSV_FORMAT1"}
    response = requests.post("http://localhost:5000/ingest", files=files, data=data)
```

Returns a data quality report including:
- Records processed, valid, and failed
- Success rate percentage
- New accounts created
- Custodians detected
- Error and warning messages

**Supported formats:**
- `CSV_FORMAT1`: Trade data in CSV format (TradeDate, AccountID, Ticker, Quantity, Price, TradeType, SettlementDate)
- `PIPE_FORMAT2`: Trade data in pipe-delimited format (REPORT_DATE|ACCOUNT_ID|SECURITY_TICKER|SHARES|MARKET_VALUE|SOURCE_SYSTEM)
- `YAML_POSITIONS`: Bank position data in YAML format

### Query Positions
```
GET /positions?account=ACC001&date=2026-01-15
```

Returns positions for the specified account and date, including:
- Shares held
- Market value
- Cost basis (calculated from trade history)
- Unrealized P&L
- Total account market value

**Parameters:**
- `account` (required): Account ID (e.g., ACC001)
- `date` (required): Date in YYYY-MM-DD format

### Compliance Concentration Check
```
GET /compliance/concentration?date=2026-01-15
```

Checks for positions exceeding 20% concentration threshold within an account.

Returns:
- Number of violations found
- Details for each violation including:
  - Account ID and ticker
  - Shares and market value
  - Concentration percentage
  - Excess percentage over threshold

**Parameters:**
- `date` (required): Date in YYYY-MM-DD format

### Reconciliation
```
GET /reconciliation?date=2026-01-15
```

Reconciles calculated positions from trade history against bank position file.

Returns:
- Total positions in bank file vs. calculated from trades
- Number of discrepancies found
- Details for each discrepancy including:
  - Account ID and ticker
  - Expected shares (from trades)
  - Actual shares (from bank)
  - Difference
  - Status (missing_in_bank, missing_in_trades, quantity_mismatch)

**Parameters:**
- `date` (required): Date in YYYY-MM-DD format

## Database Schema

### Accounts Table
Stores account master data with custodian relationships.

| Column | Type | Description |
|--------|------|-------------|
| account_id | String (PK) | Unique account identifier |
| custodian_name | String | Custodian name (e.g., CUSTODIAN_A) |
| created_at | DateTime | Account creation timestamp |

### Trades Table
Unified trade data from multiple file formats.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-increment ID |
| trade_date | Date | Trade execution date |
| account_id | String (FK) | Account identifier |
| ticker | String | Security ticker symbol |
| quantity | Integer | Shares traded (negative for SELL) |
| price | Decimal | Price per share (Format 1) |
| trade_type | String | BUY or SELL (Format 1) |
| settlement_date | Date | Settlement date (Format 1) |
| market_value | Decimal | Total trade value |
| source_system | String | Custodian system (Format 2) |
| created_at | DateTime | Record creation timestamp |

**Indexes:** (trade_date, account_id), (trade_date, ticker)

### Positions Table
Bank position snapshots from custodian reports.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-increment ID |
| report_date | Date | Position report date |
| account_id | String (FK) | Account identifier |
| ticker | String | Security ticker symbol |
| shares | Integer | Shares held |
| market_value | Decimal | Current market value |
| custodian_ref | String | Custodian reference (e.g., CUST_A_12345) |
| created_at | DateTime | Record creation timestamp |

**Indexes:** (report_date, account_id), (report_date, ticker)

## Custodian Tracking

The system correlates custodian information across different data sources:

- **Trade Format 2** includes `SOURCE_SYSTEM` field (e.g., CUSTODIAN_A, CUSTODIAN_B, CUSTODIAN_C)
- **Bank Positions** include `custodian_ref` field (e.g., CUST_A_12345, CUST_B_22345, CUST_C_99999)
- The system extracts the custodian identifier from the reference prefix:
  - `CUST_A_*` → `CUSTODIAN_A`
  - `CUST_B_*` → `CUSTODIAN_B`
  - `CUST_C_*` → `CUSTODIAN_C`
- Accounts are automatically associated with custodians during ingestion
- This enables tracking which custodian holds which positions and validates data consistency

## Process Flow

### 1. Data Ingestion
```
File Upload → Format Detection → Validation (Pydantic) → Transformation → Database Insert
```

**Validation checks:**
- Date format validation
- Required fields presence
- Data type correctness
- Business rule validation (e.g., settlement date >= trade date)
- Sign consistency (market value matches shares direction)

**Transformation logic:**
- Trade Format 1: Calculate market_value from quantity × price
- Trade Format 2: Derive price from market_value ÷ shares
- Negative quantity for SELL trades in Format 1
- Date parsing (YYYY-MM-DD for Format 1, YYYYMMDD for Format 2 and YAML)
- Custodian extraction and account association

### 2. Position Query
```
Query Parameters → Fetch Bank Positions → Calculate Cost Basis from Trades → Compute P&L → Return Results
```

- Retrieves position snapshot from bank file
- Aggregates historical trades up to query date
- Calculates weighted average cost basis
- Computes unrealized P&L (market value - total cost)
- Fallback: Calculates positions from trades if no bank data available

### 3. Compliance Check
```
Query Date → Fetch All Positions → Group by Account → Calculate Concentrations → Flag Violations
```

- Groups positions by account
- Calculates each position's percentage of total account value
- Flags positions exceeding 20% threshold
- Returns violation details with excess percentage

### 4. Reconciliation
```
Query Date → Calculate Expected Positions from Trades → Fetch Bank Positions → Compare → Report Discrepancies
```

- Aggregates all trades up to query date to calculate expected positions
- Compares against bank position file
- Identifies:
  - Missing positions (in trades but not in bank)
  - Extra positions (in bank but not in trades)
  - Quantity mismatches (different share counts)

## Logging

Logs are stored in `logs/` directory with the following features:

- **Configurable levels:** Set via `LOG_LEVEL` environment variable (DEBUG, INFO, WARNING, ERROR)
- **Auto-rotation:** Each run creates a new timestamped log file
- **Backup:** Previous logs are automatically backed up with timestamp
- **Symlink:** `logs/app_current.log` always points to the latest log
- **Request/Response logging:** All API requests and responses are logged with metadata

**Log format:**
```
YYYY-MM-DD HH:MM:SS | LEVEL    | module_name | message
```

**Logged information:**
- API requests (method, path, parameters, remote IP)
- API responses (status code, size)
- Ingestion operations (files processed, records, errors)
- Data quality issues
- Errors and exceptions with stack traces

## Sample Data

The `sample_data/` directory contains test files with intentional discrepancies:

### Trade Format Equivalence

**IMPORTANT:** The two trade file formats contain the **same trade data** in different structures:
- `trades_format1.csv` - CSV format with price, trade_type, settlement_date
- `trades_format2.txt` - Pipe-delimited format with market_value, source_system

Both represent the same 10 trades on 2026-01-15. The system can ingest either format and unify them into a single schema. **In production, only ingest one format to avoid duplicating data.** The demo script ingests Format 1 by default, then demonstrates Format 2 equivalence separately.

### Known Discrepancies
1. **ACC001 GOOGL:** 100 shares in trades vs. 75 shares in bank positions (quantity mismatch)
2. **ACC002 GOOGL:** 75 shares in trades vs. missing in bank positions
3. **ACC003 TSLA:** -150 shares (SELL) in trades vs. 80 shares in bank positions

These discrepancies are intentional to demonstrate the reconciliation functionality.

### Compliance Violations
The sample data includes positions exceeding the 20% concentration threshold to demonstrate compliance checking.

## Testing

Run the comprehensive unit test suite:

```bash
python -m pytest tests/ -v
```

**Test coverage:**
- Database model creation and relationships
- Custodian extraction logic
- Data ingestion for all formats
- Data quality validation
- Format unification
- All API endpoints
- Cost basis calculation
- Compliance violation detection
- Reconciliation discrepancy detection

## Demo Modes

The demo script (`demo.py`) supports two modes:

### Interactive TUI Mode (default)

Full interactive terminal UI using Textual:

```bash
# Start server and run TUI
./run.sh

# Ingest CSV format (Format 1)
./run.sh --format 1

# Or ingest Pipe format (Format 2)
./run.sh --format 2

# Or ingest both for format comparison
./run.sh --format both
```

**Interactive Features:**
- **Multi-screen interface** with hotkey navigation:
  - **[I]** - Ingest screen: file upload statistics and format comparison
  - **[C]** - Compliance screen: concentration violations (>20% threshold)
  - **[R]** - Reconciliation screen: trade vs bank position discrepancies
  - **[Q]** - Quit application
- **Account selector**: Arrow keys to browse accounts, Enter to select
- **Sidebar summaries**: Quick stats and filters
- **Auto-ingestion**: Files uploaded on startup based on --format flag
- **Color-coded tables**: Red for violations/discrepancies, green for matches
- **Scrollable views**: Navigate large datasets with keyboard/mouse
- **Format-aware**: De-duplicates data when --format both is used

### Simple ASCII Mode

Minimal text output for scripting/automation:

```bash
# Simple text output (defaults to Format 1)
./run.sh --simple

# Simple output with Format 1
./run.sh --simple --format 1

# Simple output with Format 2
./run.sh --simple --format 2

# Simple output with both formats (shows comparison)
./run.sh --simple --format both
```

**Simple Mode Output:**
- Portfolio positions sorted by account and ticker
- Reconciliation discrepancies with expected vs actual shares
- Compliance violations with concentration percentages
- Format comparison when using --format both
- Clean ASCII output suitable for logs or pipelines
- No emojis, colors, or interactive elements

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | sqlite:///portfolio.db | Database connection string |
| LOG_LEVEL | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |


## Production Considerations

For production deployment, consider:

1. **Database:** Use PostgreSQL or MySQL instead of SQLite
2. **Authentication:** Add API authentication/authorization
3. **Rate limiting:** Implement request rate limiting
4. **File upload:** Add secure file upload endpoint instead of file paths
5. **Async processing:** Use task queue (Celery) for large file ingestion
6. **Monitoring:** Add APM and health check monitoring
7. **Data retention:** Implement log and data archival policies
8. **Validation:** Add more comprehensive data quality rules
9. **Concurrency:** Add database transaction isolation for concurrent operations
10. **Security:** Add input sanitization, SQL injection protection, and HTTPS

