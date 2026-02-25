import importlib
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = REPO_ROOT / "backend"


class ReviewAndGoalsFlowTest(unittest.TestCase):
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

    def test_review_queue_mapping_transaction_update_and_goals(self) -> None:
        session_mod = importlib.import_module("app.db.session")
        base_mod = importlib.import_module("app.db.base")
        models = importlib.import_module("app.models")
        review_route = importlib.import_module("app.api.routes.review_queue")
        merchant_map_route = importlib.import_module("app.api.routes.merchant_map")
        tx_route = importlib.import_module("app.api.routes.transactions")
        goals_route = importlib.import_module("app.api.routes.goals")
        schemas = importlib.import_module("app.schemas")

        base_mod.Base.metadata.create_all(bind=session_mod.engine)
        db = session_mod.SessionLocal()
        try:
            db.add(models.User(id=1))
            db.add_all(
                [
                    models.FctTransaction(
                        user_id=1,
                        txn_date=date(2025, 12, 31),
                        amount=-120.0,
                        description_raw="PAYPAL *STEAM GAMES",
                        merchant_key="STEAM GAMES",
                        category="Unknown",
                        is_income=False,
                        is_movement=False,
                        is_high_impact=True,
                        txn_hash="a1",
                        user_confirmed=False,
                    ),
                    models.FctTransaction(
                        user_id=1,
                        txn_date=date(2025, 12, 30),
                        amount=-30.0,
                        description_raw="PAYPAL *STEAM GAMES",
                        merchant_key="STEAM GAMES",
                        category="Unknown",
                        is_income=False,
                        is_movement=False,
                        is_high_impact=False,
                        txn_hash="a2",
                        user_confirmed=False,
                    ),
                    models.FctTransaction(
                        user_id=1,
                        txn_date=date(2025, 12, 1),
                        amount=1000.0,
                        description_raw="Salary",
                        merchant_key="SALARY",
                        category="Other",
                        is_income=True,
                        is_movement=False,
                        is_high_impact=False,
                        txn_hash="a3",
                        user_confirmed=False,
                    ),
                    models.FctTransaction(
                        user_id=1,
                        txn_date=date(2025, 11, 15),
                        amount=-700.0,
                        description_raw="Transfer To Friend PayID",
                        merchant_key="TRANSFER TO FRIEND PAYID",
                        category="Unknown",
                        is_income=False,
                        is_movement=True,
                        is_high_impact=False,
                        txn_hash="a4",
                        user_confirmed=False,
                    ),
                ]
            )
            db.commit()

            current_user = db.query(models.User).filter(models.User.id == 1).one()
            queue = review_route.get_review_queue(db=db, current_user=current_user)
            self.assertEqual(len(queue.unknown_merchants), 2)
            self.assertEqual(queue.unknown_merchants[0].merchant_key, "STEAM GAMES")
            self.assertEqual(len(queue.large_movements), 1)
            self.assertEqual(len(queue.high_impact_spend), 1)

            tx_list = tx_route.list_transactions(
                db=db,
                current_user=current_user,
                month="2025-12",
                category=None,
                search="steam",
                only_unreviewed=True,
                include_movements=False,
                limit=50,
                offset=0,
            )
            self.assertEqual(tx_list.total, 2)
            self.assertEqual(len(tx_list.items), 2)

            months_resp = tx_route.list_transaction_months(db=db, current_user=current_user)
            self.assertIn("2025-12", months_resp.months)
            self.assertIn("2025-11", months_resp.months)

            bulk_resp = tx_route.bulk_update_transactions(
                payload=schemas.TransactionBulkUpdateRequest(
                    transaction_ids=[item.id for item in tx_list.items],
                    category="Entertainment",
                    user_confirmed=True,
                ),
                db=db,
                current_user=current_user,
            )
            self.assertEqual(bulk_resp.updated_count, 2)

            map_resp = merchant_map_route.update_merchant_map(
                payload=schemas.MerchantMapUpdateRequest(
                    merchant_key="STEAM GAMES", category="Entertainment", apply_to_existing=True
                ),
                db=db,
                current_user=current_user,
            )
            self.assertEqual(map_resp.updated_transactions, 2)

            updated_tx = (
                db.query(models.FctTransaction)
                .filter(models.FctTransaction.txn_hash == "a1")
                .one()
            )
            self.assertEqual(updated_tx.category, "Entertainment")
            self.assertTrue(updated_tx.user_confirmed)

            tx_resp = tx_route.update_transaction(
                transaction_id=updated_tx.id,
                payload=schemas.TransactionUpdateRequest(category="Shopping"),
                db=db,
                current_user=current_user,
            )
            self.assertEqual(tx_resp.category, "Shopping")

            goals_resp = goals_route.update_goals(
                payload=schemas.GoalsRequest(
                    reported_total_savings=500.0,
                    goal_amount=5000.0,
                    target_date=date(2026, 12, 31),
                ),
                db=db,
                current_user=current_user,
            )
            self.assertIn(goals_resp.feasibility_status, {"Comfortable", "On track", "At risk", "Unrealistic", "Unknown"})
            self.assertGreaterEqual(goals_resp.months_remaining, 0)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
