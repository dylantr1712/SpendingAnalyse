import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = REPO_ROOT / "backend"


class LocalAuthTest(unittest.TestCase):
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

    def test_setup_and_login(self) -> None:
        session_mod = importlib.import_module("app.db.session")
        base_mod = importlib.import_module("app.db.base")
        models = importlib.import_module("app.models")
        auth_route = importlib.import_module("app.api.routes.auth")
        schemas = importlib.import_module("app.schemas")

        base_mod.Base.metadata.create_all(bind=session_mod.engine)
        db = session_mod.SessionLocal()
        try:
            db.add(models.User(id=1))
            db.commit()

            setup_resp = auth_route.auth_setup(
                payload=schemas.AuthSetupRequest(username="localuser", password="secret123"),
                db=db,
                credentials=None,
            )
            self.assertTrue(setup_resp.configured)
            self.assertEqual(setup_resp.username, "localuser")

            status_resp = auth_route.auth_status(db=db)
            self.assertTrue(status_resp.configured)

            login_resp = auth_route.auth_login(
                payload=schemas.AuthLoginRequest(username="localuser", password="secret123"),
                db=db,
            )
            self.assertTrue(login_resp.ok)
            self.assertEqual(login_resp.username, "localuser")
        finally:
            db.close()

    def test_register_when_unconfigured(self) -> None:
        session_mod = importlib.import_module("app.db.session")
        base_mod = importlib.import_module("app.db.base")
        models = importlib.import_module("app.models")
        auth_route = importlib.import_module("app.api.routes.auth")
        schemas = importlib.import_module("app.schemas")

        base_mod.Base.metadata.create_all(bind=session_mod.engine)
        db = session_mod.SessionLocal()
        try:
            db.add(models.User(id=1))
            db.commit()

            reg_resp = auth_route.auth_register(
                payload=schemas.AuthRegisterRequest(username="newuser", password="pw12345"),
                db=db,
            )
            self.assertTrue(reg_resp.configured)
            self.assertEqual(reg_resp.username, "newuser")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
