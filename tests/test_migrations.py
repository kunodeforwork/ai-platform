from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_alembic_upgrade_creates_agents_table(tmp_path) -> None:
    database_path = tmp_path / "migration.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    columns = {column["name"]: column for column in inspect(engine).get_columns("agents")}
    assert set(columns) == {"id", "name", "description", "system_prompt", "created_at"}
    assert columns["name"]["nullable"] is False
    assert columns["name"]["type"].length == 100
    assert columns["description"]["type"].length == 500
    assert columns["description"]["default"] in {"''", ""}
    assert columns["system_prompt"]["type"].length == 4000

    command.downgrade(config, "base")
    assert "agents" not in inspect(engine).get_table_names()
