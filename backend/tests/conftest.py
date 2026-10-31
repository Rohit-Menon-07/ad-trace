from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def real_db(tmp_path_factory) -> Path:
    """The real workbook ingested + extracted into a temp DB (skipped when data/raw is absent)."""
    from backend.app.config import repo_path
    from backend.app.ingest.run import ingest

    xlsx = repo_path("raw_xlsx")
    if not xlsx.exists():
        pytest.skip("raw workbook not present (data/raw is git-ignored)")
    db = tmp_path_factory.mktemp("real") / "adtrace.db"
    ingest(xlsx, db, write_docs=False)
    return db
