"""
Unit tests for portfolio reconciliation system.
"""
import unittest
import os
import tempfile
from datetime import date
from decimal import Decimal

from models import init_db, get_session, Account, Trade, Position
from ingestion import (
    ingest_trade_format1,
    ingest_trade_format2,
    ingest_bank_positions,
    extract_custodian_name,
)
from app import app


class TestModels(unittest.TestCase):
    """Test database models."""

    def setUp(self):
        """Set up test database."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_file.close()
        self.db_url = f"sqlite:///{self.db_file.name}"
        self.engine = init_db(self.db_url)
        self.session = get_session(self.engine)

    def tearDown(self):
        """Clean up test database."""
        self.session.close()
        os.unlink(self.db_file.name)

    def test_account_creation(self):
        """Test account creation."""
        account = Account(account_id="TEST001", custodian_name="TEST_CUSTODIAN")
        self.session.add(account)
        self.session.commit()

        retrieved = self.session.query(Account).filter_by(account_id="TEST001").first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.custodian_name, "TEST_CUSTODIAN")

    def test_trade_creation(self):
        """Test trade record creation."""
        account = Account(account_id="TEST001")
        self.session.add(account)
        self.session.commit()

        trade = Trade(
            trade_date=date(2025, 1, 15),
            account_id="TEST001",
            ticker="AAPL",
            quantity=100,
            price=Decimal("185.50"),
            trade_type="BUY",
            file_format="CSV_FORMAT1",
        )
        self.session.add(trade)
        self.session.commit()

        retrieved = self.session.query(Trade).first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.ticker, "AAPL")
        self.assertEqual(retrieved.quantity, 100)


class TestCustodianExtraction(unittest.TestCase):
    """Test custodian name extraction."""

    def test_extract_custodian_name(self):
        """Test custodian extraction from reference."""
        self.assertEqual(extract_custodian_name("CUST_A_12345"), "CUSTODIAN_A")
        self.assertEqual(extract_custodian_name("CUST_B_22345"), "CUSTODIAN_B")
        self.assertEqual(extract_custodian_name("CUST_C_99999"), "CUSTODIAN_C")

    def test_invalid_custodian_ref(self):
        """Test handling of invalid custodian reference."""
        self.assertIsNone(extract_custodian_name(""))
        self.assertIsNone(extract_custodian_name(None))


class TestIngestion(unittest.TestCase):
    """Test data ingestion."""

    def setUp(self):
        """Set up test database."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_file.close()
        self.db_url = f"sqlite:///{self.db_file.name}"
        self.engine = init_db(self.db_url)
        self.session = get_session(self.engine)

    def tearDown(self):
        """Clean up test database."""
        self.session.close()
        os.unlink(self.db_file.name)

    def test_ingest_format1(self):
        """Test ingestion of CSV trade format."""
        report = ingest_trade_format1(
            self.session, "sample_data/trades_format1.csv"
        )

        self.assertEqual(report.records_processed, 10)
        self.assertEqual(report.records_valid, 10)
        self.assertEqual(report.records_failed, 0)

        # Verify trades in database
        trades = self.session.query(Trade).all()
        self.assertEqual(len(trades), 10)

        # Verify SELL trade has negative quantity
        sell_trade = (
            self.session.query(Trade)
            .filter_by(ticker="TSLA", trade_type="SELL")
            .first()
        )
        self.assertIsNotNone(sell_trade)
        self.assertEqual(sell_trade.quantity, -150)

    def test_ingest_format2(self):
        """Test ingestion of pipe-delimited trade format."""
        report = ingest_trade_format2(
            self.session, "sample_data/trades_format2.txt"
        )

        self.assertEqual(report.records_processed, 10)
        self.assertEqual(report.records_valid, 10)
        self.assertEqual(report.records_failed, 0)
        self.assertIn("CUSTODIAN_A", report.custodians_detected)
        self.assertIn("CUSTODIAN_B", report.custodians_detected)

        # Verify custodian assignment
        account = self.session.query(Account).filter_by(account_id="ACC001").first()
        self.assertEqual(account.custodian_name, "CUSTODIAN_A")

    def test_ingest_bank_positions(self):
        """Test ingestion of bank position file."""
        report = ingest_bank_positions(
            self.session, "sample_data/bank_positions.yaml"
        )

        self.assertEqual(report.records_processed, 9)
        self.assertEqual(report.records_valid, 9)
        self.assertEqual(report.records_failed, 0)

        # Verify positions in database
        positions = self.session.query(Position).all()
        self.assertEqual(len(positions), 9)

        # Verify custodian extraction and assignment
        account = self.session.query(Account).filter_by(account_id="ACC001").first()
        self.assertEqual(account.custodian_name, "CUSTODIAN_A")


class TestEndpoints(unittest.TestCase):
    """Test Flask API endpoints."""

    def setUp(self):
        """Set up test client and database."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_file.close()
        test_db_url = f"sqlite:///{self.db_file.name}"

        # Initialize test database
        test_engine = init_db(test_db_url)
        session = get_session(test_engine)

        # Ingest test data
        ingest_trade_format1(session, "sample_data/trades_format1.csv")
        ingest_trade_format2(session, "sample_data/trades_format2.txt")
        ingest_bank_positions(session, "sample_data/bank_positions.yaml")

        session.close()

        # Now set up Flask app to use test database
        import app as app_module
        # Replace the engine in the app module
        app_module.engine = test_engine

        self.app = app_module.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        """Clean up test database."""
        os.unlink(self.db_file.name)
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

    def test_health_endpoint(self):
        """Test health check endpoint."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "healthy")

    def test_ingest_endpoint(self):
        """Test ingest endpoint with file upload."""
        with open("sample_data/trades_format1.csv", "rb") as f:
            data = {
                "file": (f, "trades_format1.csv"),
                "file_format": "CSV_FORMAT1"
            }
            response = self.client.post(
                "/ingest",
                data=data,
                content_type="multipart/form-data"
            )

        self.assertIn(response.status_code, [200, 207])  # 207 for partial success
        response_data = response.get_json()
        self.assertIn("records_processed", response_data)

    def test_positions_endpoint(self):
        """Test positions endpoint."""
        response = self.client.get("/positions?account=ACC001&date=2026-01-15")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["account_id"], "ACC001")
        self.assertIsInstance(data["positions"], list)
        self.assertGreater(len(data["positions"]), 0)

        # Verify cost basis calculation
        for position in data["positions"]:
            self.assertIn("cost_basis", position)
            self.assertIn("market_value", position)

    def test_compliance_endpoint(self):
        """Test compliance concentration endpoint."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("from_trades", data)
        self.assertIn("from_bank", data)

        # Verify from_trades structure
        from_trades = data["from_trades"]
        self.assertIn("violations", from_trades)
        self.assertIn("violations_found", from_trades)

        # Verify violations structure
        if from_trades["violations_found"] > 0:
            violation = from_trades["violations"][0]
            self.assertIn("concentration_pct", violation)
            self.assertIn("threshold_pct", violation)
            self.assertGreater(violation["concentration_pct"], 20.0)

    def test_reconciliation_endpoint(self):
        """Test reconciliation endpoint."""
        response = self.client.get("/reconciliation?date=2026-01-15")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("discrepancies", data)
        self.assertIn("discrepancies_found", data)

        # Based on sample data, there should be discrepancies
        # (ACC001 GOOGL: 100 in trades vs 75 in bank)
        self.assertGreater(data["discrepancies_found"], 0)

        # Find the GOOGL discrepancy for ACC001
        googl_discrepancy = next(
            (d for d in data["discrepancies"]
             if d["account_id"] == "ACC001" and d["ticker"] == "GOOGL"),
            None
        )
        self.assertIsNotNone(googl_discrepancy)
        # Both Format1 and Format2 have 100 shares each for ACC001 GOOGL
        self.assertEqual(googl_discrepancy["expected_shares"], 200)
        self.assertEqual(googl_discrepancy["actual_shares"], 75)


class TestDataQuality(unittest.TestCase):
    """Test data quality and validation."""

    def setUp(self):
        """Set up test database."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_file.close()
        self.db_url = f"sqlite:///{self.db_file.name}"
        self.engine = init_db(self.db_url)
        self.session = get_session(self.engine)

    def tearDown(self):
        """Clean up test database."""
        self.session.close()
        os.unlink(self.db_file.name)

    def test_format_unification(self):
        """Test that both trade formats are unified correctly."""
        # Ingest both formats
        ingest_trade_format1(self.session, "sample_data/trades_format1.csv")
        ingest_trade_format2(self.session, "sample_data/trades_format2.txt")

        # Verify both formats coexist in same table
        trades = self.session.query(Trade).all()
        self.assertEqual(len(trades), 20)  # 10 from each format

        # Verify format tracking
        format1_count = (
            self.session.query(Trade).filter_by(file_format="CSV_FORMAT1").count()
        )
        format2_count = (
            self.session.query(Trade).filter_by(file_format="PIPE_FORMAT2").count()
        )
        self.assertEqual(format1_count, 10)
        self.assertEqual(format2_count, 10)

    def test_reconciliation_discrepancies(self):
        """Test that reconciliation correctly identifies known discrepancies."""
        # NOTE: This test ingests BOTH formats to verify format unification works.
        # In production, you would only ingest one format to avoid duplicates.
        # Both formats contain the same trade data in different structures.
        ingest_trade_format1(self.session, "sample_data/trades_format1.csv")
        ingest_trade_format2(self.session, "sample_data/trades_format2.txt")
        ingest_bank_positions(self.session, "sample_data/bank_positions.yaml")

        # Calculate expected positions from trades
        trades = (
            self.session.query(Trade)
            .filter(Trade.account_id == "ACC001", Trade.ticker == "GOOGL")
            .all()
        )
        expected_googl = sum(t.quantity for t in trades)
        # Both Format1 (100) and Format2 (100) = 200 total
        self.assertEqual(expected_googl, 200)

        # Get actual position from bank
        position = (
            self.session.query(Position)
            .filter(Position.account_id == "ACC001", Position.ticker == "GOOGL")
            .first()
        )
        self.assertEqual(position.shares, 75)

        # Verify discrepancy
        self.assertNotEqual(expected_googl, position.shares)


if __name__ == "__main__":
    unittest.main()
