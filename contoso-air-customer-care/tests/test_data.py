from data import generate_data as gen


def test_dataset_is_valid():
    assert gen.validate_dataset(gen.build_dataset()) == []


def test_generation_is_deterministic():
    assert gen.build_dataset() == gen.build_dataset()


def test_committed_files_match_generator():
    assert gen.check_files(gen.build_dataset()) == []


def test_validation_detects_broken_hero():
    ds = gen.build_dataset()
    hero = next(r for r in ds["reservations.json"]["reservations"] if r["confirmationCode"] == "CT8K2P")
    hero["cabin"] = "Main Cabin"
    assert "hero reservation does not match spec" in gen.validate_dataset(ds)


def test_scenario_customers_have_expected_reservations():
    ds = gen.build_dataset()
    reservations = ds["reservations.json"]["reservations"]
    tomorrow = "2026-05-15"

    def upcoming(cid):
        return [r for r in reservations if r["primaryCustomerId"] == cid and r["status"] == "Confirmed"
                and any(s["date"] >= "2026-05-14" for s in r["segments"])]

    assert [r["confirmationCode"] for r in upcoming("CUST-1007")] == ["CT8K2P"]
    assert upcoming("CUST-1019") == []
    d4 = upcoming("CUST-1024")[0]
    assert d4["segments"][0]["segmentStatus"] == "Cancelled" and d4["segments"][0]["flightNumber"] == "CT472"
    ct218_parties = [r for r in reservations if any(s["flightNumber"] == "CT218" and s["date"] == tomorrow
                                                     for s in r["segments"])]
    assert len(ct218_parties) == 3  # the Johnsons plus two other affected parties
