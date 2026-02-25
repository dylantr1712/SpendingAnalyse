import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = REPO_ROOT / "backend"


class StartupSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(BACKEND_PATH))
        self.tmpdir = tempfile.TemporaryDirectory()
        self.sqlite_path = Path(self.tmpdir.name) / "app.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.sqlite_path}"

        # Force modules to reload so they pick up DATABASE_URL from the test env.
        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                sys.modules.pop(name)

    def tearDown(self) -> None:
        os.environ.pop("DATABASE_URL", None)
        if str(BACKEND_PATH) in sys.path:
            sys.path.remove(str(BACKEND_PATH))
        self.tmpdir.cleanup()

    def test_startup_creates_schema_and_default_user_idempotently(self) -> None:
        main = importlib.import_module("app.main")
        session_mod = importlib.import_module("app.db.session")
        models = importlib.import_module("app.models")

        # Run twice to verify idempotency.
        main.ensure_default_user()
        main.ensure_default_user()

        db = session_mod.SessionLocal()
        try:
            user = db.query(models.User).filter(models.User.id == 1).first()
            self.assertIsNotNone(user)
        finally:
            db.close()

        self.assertEqual(main.health(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
