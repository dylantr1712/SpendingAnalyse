import importlib
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = REPO_ROOT / "backend"


class DashboardInsightsTest(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(BACKEND_PATH))
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(self.tmpdir.name) / 'app.db'}"
        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                sys.modules.pop(name)

    def tearDown(self) -> None:
        os.environ.pop("DATABASE_URL", None)
        if str(BACKEND_PATH) in sys.path:
            sys.path.remove(str(BACKEND_PATH))
        self.tmpdir.cleanup()

    def test_dashboard_returns_breakdowns_and_insights(self) -> None:
        session_mod = importlib.import_module("app.db.session")
        base_mod = importlib.import_module("app.db.base")
        models = importlib.import_module("app.models")
        dashboard_route = importlib.import_module("app.api.routes.dashboard")

        base_mod.Base.metadata.create_all(bind=session_mod.engine)
        db = session_mod.SessionLocal()
        try:
            user = models.User(id=1)
            db.add(user)
            db.add_all(
                [
                    # Prior months establish baseline
                    models.FctTransaction(user_id=1, txn_date=date(2025, 7, 10), amount=2000, description_raw="Salary", merchant_key="SALARY", category="Other", is_income=True, is_movement=False, is_high_impact=False, txn_hash="d1", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 7, 11), amount=-40, description_raw="Netflix", merchant_key="NETFLIX", category="Subscriptions", is_income=False, is_movement=False, is_high_impact=False, txn_hash="d2", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 8, 10), amount=2000, description_raw="Salary", merchant_key="SALARY", category="Other", is_income=True, is_movement=False, is_high_impact=False, txn_hash="d3", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 8, 12), amount=-50, description_raw="Uber Eats", merchant_key="UBER EATS", category="Food Delivery", is_income=False, is_movement=False, is_high_impact=False, txn_hash="d4", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 9, 10), amount=2000, description_raw="Salary", merchant_key="SALARY", category="Other", is_income=True, is_movement=False, is_high_impact=False, txn_hash="d5", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 9, 12), amount=-45, description_raw="Netflix", merchant_key="NETFLIX", category="Subscriptions", is_income=False, is_movement=False, is_high_impact=False, txn_hash="d6", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 10, 10), amount=2000, description_raw="Salary", merchant_key="SALARY", category="Other", is_income=True, is_movement=False, is_high_impact=False, txn_hash="d7", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 10, 12), amount=-60, description_raw="Uber Eats", merchant_key="UBER EATS", category="Food Delivery", is_income=False, is_movement=False, is_high_impact=False, txn_hash="d8", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 11, 10), amount=2000, description_raw="Salary", merchant_key="SALARY", category="Other", is_income=True, is_movement=False, is_high_impact=False, txn_hash="d9", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 11, 12), amount=-55, description_raw="Netflix", merchant_key="NETFLIX", category="Subscriptions", is_income=False, is_movement=False, is_high_impact=False, txn_hash="d10", user_confirmed=False),
                    # Current month (latest)
                    models.FctTransaction(user_id=1, txn_date=date(2025, 12, 2), amount=-220, description_raw="Apple Store", merchant_key="APPLE", category="Shopping", is_income=False, is_movement=False, is_high_impact=True, txn_hash="d11", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 12, 3), amount=-50, description_raw="Netflix", merchant_key="NETFLIX", category="Subscriptions", is_income=False, is_movement=False, is_high_impact=False, txn_hash="d12", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 12, 5), amount=-20, description_raw="Mystery Merchant", merchant_key="MYSTERY", category="Unknown", is_income=False, is_movement=False, is_high_impact=False, txn_hash="d13", user_confirmed=False),
                    models.FctTransaction(user_id=1, txn_date=date(2025, 12, 9), amount=2000, description_raw="Salary", merchant_key="SALARY", category="Other", is_income=True, is_movement=False, is_high_impact=False, txn_hash="d14", user_confirmed=False),
                ]
            )
            db.commit()

            resp = dashboard_route.get_dashboard(db=db, current_user=user)
            self.assertEqual(resp.month, "2025-12")
            self.assertGreater(resp.expense_total, 0)
            self.assertTrue(resp.category_breakdown)
            self.assertTrue(resp.top_merchants)
            self.assertTrue(resp.insights)
            self.assertIsNotNone(resp.previous_month_summary)
            self.assertEqual(resp.previous_month_summary.month, "2025-11")
            self.assertIn("Shopping", {c.category for c in resp.category_breakdown})

            nov_resp = dashboard_route.get_dashboard(month="2025-11", db=db, current_user=user)
            self.assertEqual(nov_resp.month, "2025-11")
            self.assertIsNotNone(nov_resp.previous_month_summary)
            self.assertEqual(nov_resp.previous_month_summary.month, "2025-10")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
