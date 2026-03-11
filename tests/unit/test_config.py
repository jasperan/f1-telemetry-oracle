from api.config import Settings


def test_settings_defaults():
    """Settings loads with sane defaults even without .env file."""
    s = Settings()
    assert s.oracle_dsn == "localhost:1525/FREEPDB1"
    assert s.oracle_user == "f1app"
    assert s.ollama_model == "qwen3.5:35b-a3b"
    assert s.openf1_base_url == "https://api.openf1.org/v1"
    assert s.ergast_base_url == "https://ergast.com/api/f1"
