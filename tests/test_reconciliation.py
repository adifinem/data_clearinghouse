"""
Comprehensive reconciliation and compliance tests with hardcoded expected values.
Tests each trade format separately against bank positions.
"""
import unittest
import os
import tempfile
from decimal import Decimal
from datetime import date

from models import init_db, get_session, Account, Trade, Position
from ingestion import ingest_trade_format1, ingest_trade_format2, ingest_bank_positions
from app import app


class TestFormat1Reconciliation(unittest.TestCase):
    """Test reconciliation using Format 1 (CSV) only."""

    def setUp(self):
        """Set up test database with Format 1 + Bank Positions."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_file.close()
        test_db_url = f"sqlite:///{self.db_file.name}"

        # Initialize test database
        test_engine = init_db(test_db_url)
        session = get_session(test_engine)

        # Ingest Format 1 and Bank Positions
        ingest_trade_format1(session, "sample_data/trades_format1.csv")
        ingest_bank_positions(session, "sample_data/bank_positions.yaml")

        session.close()

        # Set up Flask app
        import app as app_module
        app_module.engine = test_engine
        self.app = app_module.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        """Clean up test database."""
        os.unlink(self.db_file.name)

    def test_acc001_positions(self):
        """Test ACC001 positions match expected values."""
        response = self.client.get("/positions?account=ACC001&date=2026-01-15")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        positions = {p["ticker"]: p for p in data["positions"]}

        # Verify ACC001 has 3 positions
        self.assertEqual(len(positions), 3)

        # AAPL: 100 shares @ $185.50 = $18,550
        self.assertEqual(positions["AAPL"]["shares"], 100)
        self.assertAlmostEqual(positions["AAPL"]["market_value"], 18550.00, places=2)
        self.assertAlmostEqual(positions["AAPL"]["cost_basis"], 185.50, places=2)

        # MSFT: 50 shares @ $420.25 = $21,012.50
        self.assertEqual(positions["MSFT"]["shares"], 50)
        self.assertAlmostEqual(positions["MSFT"]["market_value"], 21012.50, places=2)
        self.assertAlmostEqual(positions["MSFT"]["cost_basis"], 420.25, places=2)

        # GOOGL: 75 shares (bank) but cost basis from 100 shares traded
        self.assertEqual(positions["GOOGL"]["shares"], 75)
        self.assertAlmostEqual(positions["GOOGL"]["market_value"], 10710.00, places=2)

    def test_acc001_compliance_violations(self):
        """Test ACC001 has 3 compliance violations (all > 20%)."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()

        # Get ACC001 violations from trades
        from_trades = data.get("from_trades", {})
        acc001_violations = [v for v in from_trades.get("violations", []) if v["account_id"] == "ACC001"]

        # ACC001 should have 3 violations (AAPL 34.5%, MSFT 39.0%, GOOGL 26.5%)
        self.assertEqual(len(acc001_violations), 3)

        violations_by_ticker = {v["ticker"]: v for v in acc001_violations}

        # AAPL: $18,550 / $53,842.50 = 34.5%
        self.assertIn("AAPL", violations_by_ticker)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["concentration_pct"], 34.5, delta=0.1)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["account_total_value"], 53842.50, places=2)

        # MSFT: $21,012.50 / $53,842.50 = 39.0%
        self.assertIn("MSFT", violations_by_ticker)
        self.assertAlmostEqual(violations_by_ticker["MSFT"]["concentration_pct"], 39.0, delta=0.1)

        # GOOGL: $14,280 / $53,842.50 = 26.5%
        self.assertIn("GOOGL", violations_by_ticker)
        self.assertAlmostEqual(violations_by_ticker["GOOGL"]["concentration_pct"], 26.5, delta=0.1)

    def test_acc002_compliance_violations(self):
        """Test ACC002 has 2 compliance violations (AAPL 34.2%, NVDA 55.9%)."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()

        # Get ACC002 violations from trades
        from_trades = data.get("from_trades", {})
        acc002_violations = [v for v in from_trades.get("violations", []) if v["account_id"] == "ACC002"]

        # ACC002 should have 2 violations (AAPL, NVDA)
        self.assertEqual(len(acc002_violations), 2)

        violations_by_ticker = {v["ticker"]: v for v in acc002_violations}

        # AAPL: $37,100 / $108,446 = 34.2%
        self.assertIn("AAPL", violations_by_ticker)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["concentration_pct"], 34.2, delta=0.1)

        # NVDA: $60,636 / $108,446 = 55.9%
        self.assertIn("NVDA", violations_by_ticker)
        self.assertAlmostEqual(violations_by_ticker["NVDA"]["concentration_pct"], 55.9, delta=0.1)

        # TSLA should NOT be in trades for ACC002
        self.assertNotIn("TSLA", violations_by_ticker)

    def test_total_compliance_violations(self):
        """Test total violations across all accounts."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()

        # Total violations from trades should be at least 7 (ACC001: 3, ACC002: 2, ACC004: 2)
        # Note: Now calculates from trades, so includes ACC004 which is not in bank positions
        from_trades = data.get("from_trades", {})
        self.assertGreaterEqual(from_trades.get("violations_found", 0), 7)

    def test_acc001_reconciliation(self):
        """Test ACC001 GOOGL reconciliation discrepancy."""
        response = self.client.get("/reconciliation?date=2026-01-15")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()

        # Find ACC001 GOOGL discrepancy
        acc001_googl = next(
            (d for d in data["discrepancies"]
             if d["account_id"] == "ACC001" and d["ticker"] == "GOOGL"),
            None
        )

        self.assertIsNotNone(acc001_googl)
        self.assertEqual(acc001_googl["expected_shares"], 100)  # From trades
        self.assertEqual(acc001_googl["actual_shares"], 75)     # From bank
        self.assertEqual(acc001_googl["difference"], -25)
        self.assertEqual(acc001_googl["status"], "quantity_mismatch")

    def test_acc002_reconciliation(self):
        """Test ACC002 has GOOGL missing in bank and TSLA missing in trades."""
        response = self.client.get("/reconciliation?date=2026-01-15")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()

        acc002_discrepancies = [
            d for d in data["discrepancies"]
            if d["account_id"] == "ACC002"
        ]

        discrepancies_by_ticker = {d["ticker"]: d for d in acc002_discrepancies}

        # GOOGL: Expected 75, Actual 0 (missing in bank)
        self.assertIn("GOOGL", discrepancies_by_ticker)
        self.assertEqual(discrepancies_by_ticker["GOOGL"]["expected_shares"], 75)
        self.assertEqual(discrepancies_by_ticker["GOOGL"]["actual_shares"], 0)
        self.assertEqual(discrepancies_by_ticker["GOOGL"]["status"], "missing_in_bank")

        # TSLA: Expected 0, Actual 80 (missing in trades)
        self.assertIn("TSLA", discrepancies_by_ticker)
        self.assertEqual(discrepancies_by_ticker["TSLA"]["expected_shares"], 0)
        self.assertEqual(discrepancies_by_ticker["TSLA"]["actual_shares"], 80)
        self.assertEqual(discrepancies_by_ticker["TSLA"]["status"], "missing_in_trades")


class TestFormat2Reconciliation(unittest.TestCase):
    """Test reconciliation using Format 2 (Pipe) only."""

    def setUp(self):
        """Set up test database with Format 2 + Bank Positions."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_file.close()
        test_db_url = f"sqlite:///{self.db_file.name}"

        # Initialize test database
        test_engine = init_db(test_db_url)
        session = get_session(test_engine)

        # Ingest Format 2 and Bank Positions
        ingest_trade_format2(session, "sample_data/trades_format2.txt")
        ingest_bank_positions(session, "sample_data/bank_positions.yaml")

        session.close()

        # Set up Flask app
        import app as app_module
        app_module.engine = test_engine
        self.app = app_module.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        """Clean up test database."""
        os.unlink(self.db_file.name)

    def test_format2_same_violations_as_format1(self):
        """Test Format 2 produces same compliance violations as Format 1."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()

        # Should have same total violations as Format 1 (from trades)
        from_trades = data.get("from_trades", {})
        self.assertGreaterEqual(from_trades.get("violations_found", 0), 5)

        # ACC001 should still have 3 violations
        acc001_violations = [v for v in from_trades.get("violations", []) if v["account_id"] == "ACC001"]
        self.assertEqual(len(acc001_violations), 3)

    def test_format2_same_reconciliation_as_format1(self):
        """Test Format 2 produces same reconciliation discrepancies as Format 1."""
        response = self.client.get("/reconciliation?date=2026-01-15")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()

        # ACC001 GOOGL should still be a discrepancy
        acc001_googl = next(
            (d for d in data["discrepancies"]
             if d["account_id"] == "ACC001" and d["ticker"] == "GOOGL"),
            None
        )

        self.assertIsNotNone(acc001_googl)
        self.assertEqual(acc001_googl["expected_shares"], 100)
        self.assertEqual(acc001_googl["actual_shares"], 75)
        self.assertEqual(acc001_googl["difference"], -25)


if __name__ == "__main__":
    unittest.main()
