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

    run_columns = {
        column["name"]: column for column in inspect(engine).get_columns("agent_runs")
    }
    assert set(run_columns) == {
        "id", "agent_id", "input", "output", "status", "error_code",
        "created_at", "completed_at",
    }
    assert {index["name"] for index in inspect(engine).get_indexes("agent_runs")} == {
        "ix_agent_runs_agent_id", "ix_agent_runs_status", "ix_agent_runs_created_at"
    }
    assert inspect(engine).get_foreign_keys("agent_runs")[0]["referred_table"] == "agents"

    command.downgrade(config, "base")
    assert "agents" not in inspect(engine).get_table_names()
    assert "agent_runs" not in inspect(engine).get_table_names()
