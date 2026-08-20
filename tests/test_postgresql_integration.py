import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from alembic import command
from chint_ai_platform.agents import Agent
from chint_ai_platform.persistence import DatabaseSessionScope, SqlAlchemyAgentRepository

POSTGRES_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")


@pytest.mark.skipif(
    not POSTGRES_TEST_DATABASE_URL,
    reason="POSTGRES_TEST_DATABASE_URL is not configured",
)
def test_postgresql_migration_and_repository_round_trip() -> None:
    assert POSTGRES_TEST_DATABASE_URL is not None
    database_name = make_url(POSTGRES_TEST_DATABASE_URL).database or ""
    assert database_name.endswith("_test"), "PostgreSQL integration requires a *_test database"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", POSTGRES_TEST_DATABASE_URL)
    command.upgrade(config, "head")
    engine = create_engine(POSTGRES_TEST_DATABASE_URL)
    factory = sessionmaker(engine)
    agent = Agent(
        str(uuid4()),
        "集成测试助手",
        "",
        "只处理测试数据",
        datetime.now(UTC),
    )
    write_scope = DatabaseSessionScope(factory)
    SqlAlchemyAgentRepository(write_scope).add(agent)
    write_scope.commit()
    write_scope.close()
    read_scope = DatabaseSessionScope(factory)
    loaded = SqlAlchemyAgentRepository(read_scope).get(agent.id)
    read_scope.close()
    assert loaded == agent
