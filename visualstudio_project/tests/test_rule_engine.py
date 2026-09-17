from src.rule_engine import evaluate_risks


def _by_code(results, code):
    return next((x for x in results if x["waste_code"] == code), None)


def test_case_1_idle_window_composite_high():
    r = evaluate_risks({"Q02": 24, "Q03": "EMPTY_51_PLUS", "Q06": "OVER_30_MIN"})
    item = _by_code(r, "PC_IDLE_WINDOW_LEAK")
    assert item is not None
    assert item["risk_score"] >= 6
    assert item["risk_level"] == "HIGH"


def test_case_2_hidden_baseload():
    r = evaluate_risks({"Q14": "DONT_KNOW_ACTIVE_LOADS", "Q15": "NEVER_CHECKED"})
    item = _by_code(r, "HIDDEN_BASELOAD_RISK")
    assert item is not None
    assert item["risk_score"] > 0


def test_case_3_immediate_sleep_is_not_risk():
    r = evaluate_risks({"Q05": "BOTH_AUTO_SAVE", "Q06": "IMMEDIATE"})
    item = _by_code(r, "PC_IDLE_WINDOW_LEAK")
    assert item is None or item["risk_score"] == 0


def test_case_4_multiple_peripherals_powered():
    r = evaluate_risks({"Q08": "MULTIPLE_POWERED"})
    assert _by_code(r, "PERIPHERAL_IDLE_POWER") is not None


def test_case_5_door_heater_always_on():
    r = evaluate_risks({"Q16": "ALWAYS_ON_KNOWN"})
    assert _by_code(r, "REFRIG_DOOR_HEATER_ALWAYS_ON") is not None


def test_case_6_defrost_unknown_needs_confirmation():
    r = evaluate_risks({"Q17": "DONT_KNOW_IF_EXISTS"})
    item = _by_code(r, "REFRIG_DEFROST_CONTROL")
    assert item is not None
    assert item["needs_confirmation"] is True


def test_case_7_unknowns_do_not_create_high_score():
    r = evaluate_risks({"Q05": "UNKNOWN", "Q06": "UNKNOWN", "Q08": "UNKNOWN", "Q09": "UNKNOWN"})
    assert r
    assert all(x["risk_score"] < 6 for x in r)
    assert any(x["needs_confirmation"] for x in r)
