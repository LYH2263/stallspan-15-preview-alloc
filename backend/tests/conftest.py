import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.seed import seed_if_empty


@pytest.fixture()
def client():
    # In-memory SQLite shared across threads via StaticPool. The app's
    # lifespan uses the module-level Postgres engine, so instantiate the
    # TestClient WITHOUT the context manager and manage the schema ourselves.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    seed_if_empty(db)
    db.close()

    def override_get_db():
        s = TestingSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def db_session(client):
    """Direct DB handle for counting run rows."""
    gen = client.app.dependency_overrides[get_db]()
    s = next(gen)
    try:
        yield s
    finally:
        s.close()
