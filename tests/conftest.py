import pytest

from scale2zwift.garmin import GarminAccount
from scale2zwift.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data")


@pytest.fixture
def garmin(store):
    return GarminAccount(store.garmin_dir)
