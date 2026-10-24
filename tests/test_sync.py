from datetime import datetime, timezone

from scale2zwift.garmin import WeighIn
from scale2zwift.sync import Syncer


class FakeGarmin:
    connected = True

    def __init__(self, weigh_in):
        self.weigh_in = weigh_in

    def fetch_latest(self):
        return self.weigh_in


class FakeZwift:
    instances = []

    def __init__(self, email, password, tokens=None, on_tokens=None):
        self.weight = 70000
        self.writes = []
        FakeZwift.instances.append(self)

    def set_weight(self, grams):
        self.writes.append(grams)
        changed = grams != self.weight
        self.weight = grams
        return changed


def make(store, weigh_in):
    store.secrets.save({"zwift_email": "rider@example.com", "zwift_password": "x"})
    FakeZwift.instances.clear()
    return Syncer(store, FakeGarmin(weigh_in), zwift_factory=FakeZwift)


WEIGH_IN = WeighIn(sample_pk=1, grams=72500, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), source="INDEX_SCALE")


def test_new_weigh_in_is_pushed_once(store):
    syncer = make(store, WEIGH_IN)
    assert syncer.run()["status"] == "updated"
    assert syncer.run()["status"] == "skipped"
    assert [w for z in FakeZwift.instances for w in z.writes] == [72500]
    assert store.state.load()["synced_sample_pk"] == 1


def test_force_pushes_again(store):
    syncer = make(store, WEIGH_IN)
    syncer.run()
    syncer.run(force=True)
    assert [w for z in FakeZwift.instances for w in z.writes] == [72500, 72500]


def test_not_configured(store):
    syncer = Syncer(store, FakeGarmin(WEIGH_IN), zwift_factory=FakeZwift)
    assert syncer.run()["status"] == "error"


def test_no_weigh_ins(store):
    assert make(store, None).run()["status"] == "skipped"


def test_errors_are_recorded_not_raised(store):
    class Broken(FakeGarmin):
        def fetch_latest(self):
            raise RuntimeError("boom")

    syncer = Syncer(store, Broken(None), zwift_factory=FakeZwift)
    store.secrets.save({"zwift_email": "rider@example.com", "zwift_password": "x"})
    event = syncer.run()
    assert event["status"] == "error" and "boom" in event["message"]
    assert store.state.load()["history"][0] == event
