from pathlib import Path

import pytest

from sql_analyst.db import ReadOnlyDatabase, build_demo_db

SEED = Path(__file__).resolve().parents[1] / "examples" / "shop.sql"


@pytest.fixture()
def db(tmp_path: Path):
    database = ReadOnlyDatabase(build_demo_db(tmp_path / "shop.db", SEED))
    yield database
    database.close()
