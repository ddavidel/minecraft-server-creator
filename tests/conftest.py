import pytest

from mcsc_gui.core import players, stats_history


@pytest.fixture(autouse=True, scope="session")
def _no_stats_database():
    """Tests never write the user's stats history (server_manager configures it on import)."""
    previous = stats_history.get_store()
    stats_history.configure(None)
    yield
    stats_history.configure(previous)


@pytest.fixture(autouse=True)
def _forget_players():
    yield
    players.stop_all()
