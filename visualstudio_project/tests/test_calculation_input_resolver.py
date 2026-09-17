from src.calculation_input_resolver import resolve_formula_inputs, resolve_survey_inputs


def test_q03_range_mapping():
    r = resolve_survey_inputs({"Q03": "EMPTY_31_50"})
    assert r["EMPTY_SEAT_RATE"]["value_min"] == 0.31
    assert r["EMPTY_SEAT_RATE"]["value_max"] == 0.50


def test_q06_over_30_has_no_invented_upper_bound():
    r = resolve_survey_inputs({"Q06": "OVER_30_MIN"})
    assert r["IDLE_TRANSITION_TIME"]["value_min"] == 30
    assert r["IDLE_TRANSITION_TIME"]["value_max"] is None


def test_missing_pc_power_is_not_invented():
    r = resolve_formula_inputs(
        "F_PC_SLEEP",
        {"Q01": 80, "Q03": "EMPTY_31_50"},
        {"PC_SAVABLE_HOURS": 2, "OCCURRENCE_DAYS": 30},
        {"PC_BASE_STATE": "idle", "PC_TARGET_STATE": "sleep"},
    )
    assert "PC_BASE_W" in r["missing_inputs"]
    assert "PC_TARGET_W" in r["missing_inputs"]


def test_user_measured_values_override_reference_need():
    r = resolve_formula_inputs(
        "F_PC_SLEEP",
        {"Q01": 80, "Q03": "EMPTY_31_50"},
        {
            "PC_MEASURED_IDLE_W": 90,
            "PC_MEASURED_SLEEP_W": 5,
            "PC_SAVABLE_HOURS": 2,
            "OCCURRENCE_DAYS": 30,
        },
        {"PC_BASE_STATE": "idle", "PC_TARGET_STATE": "sleep"},
    )
    assert not r["missing_inputs"]
    assert r["resolved"]["PC_BASE_W"]["value_min"] == 90
    assert r["resolved"]["PC_TARGET_W"]["value_min"] == 5
    assert r["resolved"]["PC_BASE_W"]["evidence_class"] == "MEASURED"
