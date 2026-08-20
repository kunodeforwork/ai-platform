from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from chint_ai_platform.agents import Agent
from chint_ai_platform.persistence import (
    Base,
    DatabaseSessionScope,
    SqlAlchemyAgentRepository,
)

AGENT = Agent(
    "5b1c53ef-6cd7-4537-81b6-d37ef87c5f69",
    "销售助手",
    "分析异常",
    "只分析销售数据",
    datetime(2026, 8, 20, 9, 30, tzinfo=UTC),
)


def test_sqlalchemy_repository_persists_agent_across_sessions(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'agents.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    write_scope = DatabaseSessionScope(factory)
    SqlAlchemyAgentRepository(write_scope).add(AGENT)
    write_scope.commit()
    write_scope.close()

    read_scope = DatabaseSessionScope(factory)
    loaded = SqlAlchemyAgentRepository(read_scope).get(AGENT.id)
    read_scope.close()

    assert loaded == AGENT


def test_sqlalchemy_repository_returns_none_for_unknown_agent(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'agents.db'}")
    Base.metadata.create_all(engine)
    scope = DatabaseSessionScope(sessionmaker(engine))

    assert SqlAlchemyAgentRepository(scope).get(AGENT.id) is None

    scope.close()


class RecordingSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closes += 1


def test_database_session_scope_is_lazy_and_reuses_session() -> None:
    session = RecordingSession()
    factory_calls = 0

    def factory() -> Session:
        nonlocal factory_calls
        factory_calls += 1
        return session  # type: ignore[return-value]

    scope = DatabaseSessionScope(factory)
    assert factory_calls == 0

    assert scope.session is session
    assert scope.session is session
    assert factory_calls == 1

    scope.commit()
    scope.rollback()
    scope.close()
    assert (session.commits, session.rollbacks, session.closes) == (1, 1, 1)
