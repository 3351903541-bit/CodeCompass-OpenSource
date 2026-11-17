from pathlib import Path
import pytest
from codecompass.product.service import Service
ROOT=Path(__file__).resolve().parents[2]
@pytest.fixture
def service(tmp_path): return Service(ROOT,tmp_path/'product.sqlite3','test_fixture')
