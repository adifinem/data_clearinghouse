"""
Comprehensive hardcoded tests for both truths (trades vs bank).
Values are based on verified math from the sample data files.
"""
import unittest
import os
import tempfile
from decimal import Decimal

from models import init_db, get_session
from ingestion import ingest_trade_format1, ingest_bank_positions
from app import app


class TestBothTruths(unittest.TestCase):
    """Test hardcoded expected values for both trade and bank truths."""

    def setUp(self):
        """Set up test database with sample data."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_file.close()
        test_db_url = f"sqlite:///{self.db_file.name}"

        # Initialize test database
        test_engine = init_db(test_db_url)
        session = get_session(test_engine)

        # Ingest both trade and bank files
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

    def test_acc001_from_trades(self):
        """Test ACC001 calculated from trades - HARDCODED VALUES."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        from_trades = data.get("from_trades", {})
        violations = from_trades.get("violations", [])

        # Get ACC001 violations
        acc001 = [v for v in violations if v["account_id"] == "ACC001"]
        self.assertEqual(len(acc001), 3, "ACC001 should have 3 violations")

        violations_by_ticker = {v["ticker"]: v for v in acc001}

        # AAPL: 100 shares @ $185.50 = $18,550.00
        # Account total: $53,842.50
        # Concentration: 34.45%
        self.assertIn("AAPL", violations_by_ticker)
        self.assertEqual(violations_by_ticker["AAPL"]["shares"], 100)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["market_value"], 18550.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["account_total_value"], 53842.50, places=2)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["concentration_pct"], 34.45, delta=0.05)

        # MSFT: 50 shares @ $420.25 = $21,012.50
        # Concentration: 39.03%
        self.assertIn("MSFT", violations_by_ticker)
        self.assertEqual(violations_by_ticker["MSFT"]["shares"], 50)
        self.assertAlmostEqual(violations_by_ticker["MSFT"]["market_value"], 21012.50, places=2)
        self.assertAlmostEqual(violations_by_ticker["MSFT"]["account_total_value"], 53842.50, places=2)
        self.assertAlmostEqual(violations_by_ticker["MSFT"]["concentration_pct"], 39.03, delta=0.05)

        # GOOGL: 100 shares @ $142.80 = $14,280.00
        # Concentration: 26.52%
        self.assertIn("GOOGL", violations_by_ticker)
        self.assertEqual(violations_by_ticker["GOOGL"]["shares"], 100)
        self.assertAlmostEqual(violations_by_ticker["GOOGL"]["market_value"], 14280.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["GOOGL"]["account_total_value"], 53842.50, places=2)
        self.assertAlmostEqual(violations_by_ticker["GOOGL"]["concentration_pct"], 26.52, delta=0.05)

    def test_acc001_from_bank(self):
        """Test ACC001 from bank positions - HARDCODED VALUES."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        from_bank = data.get("from_bank", {})
        violations = from_bank.get("violations", [])

        # Get ACC001 violations
        acc001 = [v for v in violations if v["account_id"] == "ACC001"]
        self.assertEqual(len(acc001), 3, "ACC001 should have 3 violations from bank")

        violations_by_ticker = {v["ticker"]: v for v in acc001}

        # AAPL: 100 shares, market value $18,550.00
        # Account total from bank: $50,272.50 (GOOGL is 75 shares, not 100)
        # Concentration: 36.90%
        self.assertIn("AAPL", violations_by_ticker)
        self.assertEqual(violations_by_ticker["AAPL"]["shares"], 100)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["market_value"], 18550.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["account_total_value"], 50272.50, places=2)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["concentration_pct"], 36.90, delta=0.05)

        # MSFT: 50 shares, market value $21,012.50
        # Concentration: 41.80%
        self.assertIn("MSFT", violations_by_ticker)
        self.assertEqual(violations_by_ticker["MSFT"]["shares"], 50)
        self.assertAlmostEqual(violations_by_ticker["MSFT"]["market_value"], 21012.50, places=2)
        self.assertAlmostEqual(violations_by_ticker["MSFT"]["account_total_value"], 50272.50, places=2)
        self.assertAlmostEqual(violations_by_ticker["MSFT"]["concentration_pct"], 41.80, delta=0.05)

        # GOOGL: 75 shares (bank has less!), market value $10,710.00
        # Concentration: 21.30%
        self.assertIn("GOOGL", violations_by_ticker)
        self.assertEqual(violations_by_ticker["GOOGL"]["shares"], 75)
        self.assertAlmostEqual(violations_by_ticker["GOOGL"]["market_value"], 10710.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["GOOGL"]["account_total_value"], 50272.50, places=2)
        self.assertAlmostEqual(violations_by_ticker["GOOGL"]["concentration_pct"], 21.30, delta=0.05)

    def test_acc002_from_trades(self):
        """Test ACC002 calculated from trades - HARDCODED VALUES."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        data = response.get_json()
        from_trades = data.get("from_trades", {})
        violations = from_trades.get("violations", [])

        acc002 = [v for v in violations if v["account_id"] == "ACC002"]
        self.assertEqual(len(acc002), 2, "ACC002 should have 2 violations")

        violations_by_ticker = {v["ticker"]: v for v in acc002}

        # AAPL: 200 shares @ $185.50 = $37,100.00
        # Account total: $108,446.00
        # Concentration: 34.21%
        self.assertIn("AAPL", violations_by_ticker)
        self.assertEqual(violations_by_ticker["AAPL"]["shares"], 200)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["market_value"], 37100.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["account_total_value"], 108446.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["concentration_pct"], 34.21, delta=0.05)

        # NVDA: 120 shares @ $505.30 = $60,636.00
        # Concentration: 55.91%
        self.assertIn("NVDA", violations_by_ticker)
        self.assertEqual(violations_by_ticker["NVDA"]["shares"], 120)
        self.assertAlmostEqual(violations_by_ticker["NVDA"]["market_value"], 60636.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["NVDA"]["account_total_value"], 108446.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["NVDA"]["concentration_pct"], 55.91, delta=0.05)

        # GOOGL: 75 shares but NOT in bank, so not a violation (< 10%)
        self.assertNotIn("GOOGL", violations_by_ticker)

    def test_acc003_short_position_handling(self):
        """Test ACC003 with SELL (short position) - HARDCODED VALUES."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        data = response.get_json()
        from_trades = data.get("from_trades", {})
        violations = from_trades.get("violations", [])

        acc003 = [v for v in violations if v["account_id"] == "ACC003"]

        # ACC003 has:
        # NVDA: 80 shares @ $505.30 = $40,424.00 (positive)
        # TSLA: -150 shares (SELL) = -$35,767.50 (negative - excluded from total)
        # Account total for concentration: $40,424.00 (only positive positions)
        # NVDA concentration: 100% (only positive position)

        violations_by_ticker = {v["ticker"]: v for v in acc003}

        # NVDA should be the only violation (100% concentration)
        self.assertIn("NVDA", violations_by_ticker)
        self.assertEqual(violations_by_ticker["NVDA"]["shares"], 80)
        self.assertAlmostEqual(violations_by_ticker["NVDA"]["market_value"], 40424.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["NVDA"]["account_total_value"], 40424.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["NVDA"]["concentration_pct"], 100.00, delta=0.05)

        # Concentration should NEVER exceed 100%
        for v in acc003:
            self.assertLessEqual(v["concentration_pct"], 100.0,
                               f"{v['ticker']} concentration {v['concentration_pct']}% exceeds 100%!")

        # TSLA should NOT appear (negative position excluded)
        self.assertNotIn("TSLA", violations_by_ticker)

    def test_acc004_only_in_trades(self):
        """Test ACC004 exists in trades but NOT in bank - HARDCODED VALUES."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        data = response.get_json()
        from_trades = data.get("from_trades", {})
        from_bank = data.get("from_bank", {})

        # ACC004 should have violations from trades
        acc004_trades = [v for v in from_trades.get("violations", []) if v["account_id"] == "ACC004"]
        self.assertEqual(len(acc004_trades), 2, "ACC004 should have 2 violations from trades")

        violations_by_ticker = {v["ticker"]: v for v in acc004_trades}

        # AAPL: 500 shares @ $185.50 = $92,750.00
        # Account total: $218,825.00
        # Concentration: 42.39%
        self.assertIn("AAPL", violations_by_ticker)
        self.assertEqual(violations_by_ticker["AAPL"]["shares"], 500)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["market_value"], 92750.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["account_total_value"], 218825.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["AAPL"]["concentration_pct"], 42.39, delta=0.05)

        # MSFT: 300 shares @ $420.25 = $126,075.00
        # Concentration: 57.61%
        self.assertIn("MSFT", violations_by_ticker)
        self.assertEqual(violations_by_ticker["MSFT"]["shares"], 300)
        self.assertAlmostEqual(violations_by_ticker["MSFT"]["market_value"], 126075.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["MSFT"]["account_total_value"], 218825.00, places=2)
        self.assertAlmostEqual(violations_by_ticker["MSFT"]["concentration_pct"], 57.61, delta=0.05)

        # ACC004 should NOT appear in bank violations
        acc004_bank = [v for v in from_bank.get("violations", []) if v["account_id"] == "ACC004"]
        self.assertEqual(len(acc004_bank), 0, "ACC004 should not exist in bank data")

    def test_no_concentration_over_100_percent(self):
        """Verify NO concentration ever exceeds 100% (professional constraint)."""
        response = self.client.get("/compliance/concentration?date=2026-01-15")
        data = response.get_json()

        # Check all violations from both sources
        from_trades = data.get("from_trades", {})
        from_bank = data.get("from_bank", {})

        all_violations = from_trades.get("violations", []) + from_bank.get("violations", [])

        for v in all_violations:
            self.assertLessEqual(v["concentration_pct"], 100.0,
                               f"{v['account_id']} {v['ticker']} has {v['concentration_pct']}% > 100%!")
            self.assertGreaterEqual(v["concentration_pct"], 0.0,
                                  f"{v['account_id']} {v['ticker']} has negative concentration!")


if __name__ == "__main__":
    unittest.main()
