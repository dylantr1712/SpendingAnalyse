import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = REPO_ROOT / "backend"

SAMPLE_HEADERLESS_CSV = (
    b'31/12/2025,"-17.99","CHEMIST WAREHOUSE LIVERPOOL NS AUS Card xx4147 Value Date: 27/12/2025","+5189.04"\n'
    b'30/12/2025,"+210.00","Fast Transfer From DUC VU to PayID Phone Ty Value Date: 31/12/2025","+5207.03"\n'
)


class CommBankHeaderlessIngestTest(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(BACKEND_PATH))
        self.tmpdir = tempfile.TemporaryDirectory()
        self.sqlite_path = Path(self.tmpdir.name) / "app.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.sqlite_path}"

        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                sys.modules.pop(name)

    def tearDown(self) -> None:
        os.environ.pop("DATABASE_URL", None)
        if str(BACKEND_PATH) in sys.path:
            sys.path.remove(str(BACKEND_PATH))
        self.tmpdir.cleanup()

    def test_ingests_commbank_headerless_csv(self) -> None:
        session_mod = importlib.import_module("app.db.session")
        base_mod = importlib.import_module("app.db.base")
        models = importlib.import_module("app.models")
        ingest = importlib.import_module("app.services.ingest")

        base_mod.Base.metadata.create_all(bind=session_mod.engine)

        db = session_mod.SessionLocal()
        try:
            db.add(models.User(id=1))
            db.commit()

            batch = ingest.ingest_csv(db, user_id=1, file_bytes=SAMPLE_HEADERLESS_CSV)
            self.assertEqual(batch.row_count, 2)

            rows = db.query(models.FctTransaction).order_by(models.FctTransaction.txn_date.desc()).all()
            self.assertEqual(len(rows), 2)
            self.assertAlmostEqual(rows[0].amount, -17.99, places=2)
            self.assertEqual(rows[0].txn_date.isoformat(), "2025-12-31")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
