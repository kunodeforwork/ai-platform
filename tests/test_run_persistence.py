from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chint_ai_platform.agent_runs import PersistedAgentRun
from chint_ai_platform.persistence import (
    Base,
    DatabaseSessionScope,
    SqlAlchemyAgentRunRepository,
)


def test_run_repository_adds_gets_and_updates_across_sessions(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'runs.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    created_at = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)
    running = PersistedAgentRun.start(
        "d6109938-c9ba-4bc0-a20a-27e1b1fceb67",
        None,
        "原始输入" * 100,
        created_at,
    )
    write_scope = DatabaseSessionScope(factory)
    SqlAlchemyAgentRunRepository(write_scope).add(running)
    write_scope.commit()
    write_scope.close()

    update_scope = DatabaseSessionScope(factory)
    repository = SqlAlchemyAgentRunRepository(update_scope)
    loaded = repository.get(running.id)
    assert loaded == running
    completed = running.complete("最终输出" * 100, created_at + timedelta(seconds=2))
    repository.update(completed)
    update_scope.commit()
    update_scope.close()

    read_scope = DatabaseSessionScope(factory)
    assert SqlAlchemyAgentRunRepository(read_scope).get(running.id) == completed
    assert SqlAlchemyAgentRunRepository(read_scope).get(
        "8e52ea3a-f9ec-41b8-9464-e21e4c4ef9e9"
    ) is None
    read_scope.close()


def test_run_repository_rejects_stale_terminal_update(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'runs.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    created_at = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)
    running = PersistedAgentRun.start(
        "d6109938-c9ba-4bc0-a20a-27e1b1fceb67", None, "输入", created_at
    )
    initial_scope = DatabaseSessionScope(factory)
    SqlAlchemyAgentRunRepository(initial_scope).add(running)
    initial_scope.commit()
    initial_scope.close()

    completed = running.complete("输出", created_at + timedelta(seconds=1))
    first_scope = DatabaseSessionScope(factory)
    SqlAlchemyAgentRunRepository(first_scope).update(completed)
    first_scope.commit()
    first_scope.close()

    failed = running.fail("deepseek_timeout", created_at + timedelta(seconds=2))
    stale_scope = DatabaseSessionScope(factory)
    with pytest.raises(Exception, match="Database is unavailable"):
        SqlAlchemyAgentRunRepository(stale_scope).update(failed)
    stale_scope.rollback()
    stale_scope.close()

    read_scope = DatabaseSessionScope(factory)
    assert SqlAlchemyAgentRunRepository(read_scope).get(running.id) == completed
    read_scope.close()
