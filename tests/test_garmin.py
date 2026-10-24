from scale2zwift.garmin import latest_weigh_in

# Shape of Garmin's /weight-service/weight/range response (made-up values).
RESPONSE = {
    "dailyWeightSummaries": [
        {
            "summaryDate": "2026-01-02",
            "allWeightMetrics": [
                {"samplePk": 2, "weight": 80123.4, "timestampGMT": 1767340800000, "sourceType": "INDEX_SCALE"},
            ],
        },
        {
            "summaryDate": "2026-01-01",
            "allWeightMetrics": [
                {"samplePk": 1, "weight": 81000.0, "timestampGMT": 1767254400000, "sourceType": "MANUAL"},
                {"samplePk": 9, "weight": None, "timestampGMT": 1767254500000},
            ],
        },
    ]
}


def test_latest_weigh_in_picks_most_recent():
    w = latest_weigh_in(RESPONSE)
    assert (w.sample_pk, w.grams, w.source) == (2, 80123, "INDEX_SCALE")
    assert w.timestamp.isoformat() == "2026-01-02T08:00:00+00:00"


def test_latest_weigh_in_empty():
    assert latest_weigh_in({}) is None
    assert latest_weigh_in({"dailyWeightSummaries": []}) is None
