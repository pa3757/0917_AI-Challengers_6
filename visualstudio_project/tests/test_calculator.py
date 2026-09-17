from src.calculator import calculate_all_solutions, calculate_solution_saving


PC_SOL = {
    "solution_id": "SOL_PC_003",
    "waste_code": "PC_IDLE_WINDOW_LEAK",
    "formula_id": "F_PC_SLEEP",
    "calculation_available": True,
    "requires_measurement": False,
}


def test_pc_solution_needs_input_when_power_missing():
    r = calculate_solution_saving(
        PC_SOL,
        {"Q01": 80, "Q03": "EMPTY_31_50", "Q06": "OVER_30_MIN"},
        {"PC_SAVABLE_HOURS": 2, "OCCURRENCE_DAYS": 30},
    )
    assert r["calculation_status"] == "NEEDS_INPUT"
    assert "PC_BASE_W" in r["missing_inputs"]


def test_pc_range_calculation_with_measured_power():
    r = calculate_solution_saving(
        PC_SOL,
        {"Q01": 100, "Q03": "EMPTY_31_50", "Q06": "MIN_15_30"},
        {
            "PC_MEASURED_IDLE_W": 100,
            "PC_MEASURED_SLEEP_W": 5,
            "PC_SAVABLE_HOURS": 2,
            "OCCURRENCE_DAYS": 30,
        },
    )
    assert r["calculation_status"] == "ESTIMATED"
    assert round(r["energy_saving_kwh_min"], 1) == 176.7
    assert round(r["energy_saving_kwh_max"], 1) == 285.0
    assert r["cost_saving_krw_min"] is None


def test_non_calculable_solution_stays_non_calculable():
    sol = {
        "solution_id": "SOL_HVAC_004",
        "waste_code": "HVAC_OUTDOOR_HEAT_RECIRCULATION",
        "formula_id": "",
        "calculation_available": False,
        "requires_measurement": False,
    }
    r = calculate_solution_saving(sol, {})
    assert r["calculation_status"] == "NOT_CALCULABLE"
    assert r["energy_saving_kwh_min"] is None


def test_formula_not_found_is_explicit():
    sol = {
        "solution_id": "SOL_X",
        "waste_code": "X",
        "formula_id": "FORM_DOES_NOT_EXIST",
        "calculation_available": True,
        "requires_measurement": False,
    }
    r = calculate_solution_saving(sol, {})
    assert r["calculation_status"] == "FORMULA_NOT_FOUND"


def test_tariff_missing_does_not_block_kwh():
    r = calculate_solution_saving(
        PC_SOL,
        {"Q01": 100, "Q03": "EMPTY_31_50"},
        {
            "PC_MEASURED_IDLE_W": 100,
            "PC_MEASURED_SLEEP_W": 5,
            "PC_SAVABLE_HOURS": 2,
            "OCCURRENCE_DAYS": 30,
        },
        tariff_context=None,
    )
    assert r["energy_saving_kwh_min"] is not None
    assert r["cost_saving_krw_min"] is None


def test_exact_tariff_can_calculate_energy_charge_only():
    r = calculate_solution_saving(
        PC_SOL,
        {"Q01": 100, "Q03": "EMPTY_31_50"},
        {
            "PC_MEASURED_IDLE_W": 100,
            "PC_MEASURED_SLEEP_W": 5,
            "PC_SAVABLE_HOURS": 2,
            "OCCURRENCE_DAYS": 30,
        },
        tariff_context={
            "contract_type": "GENERAL_A_I",
            "voltage_class": "LV",
            "tariff_option": "NONE",
            "season": "summer",
            "region": "MAINLAND",
            "band": "all",
        },
    )
    assert r["cost_saving_krw_min"] is not None
    assert any(ref.startswith("TARIFF_GENERAL_A_I_LV_NONE_ALL_SUMMER") for ref in r["used_references"])


def test_monthly_usage_sanity_warning():
    r = calculate_solution_saving(
        PC_SOL,
        {"Q01": 100, "Q03": "EMPTY_31_50", "Q04": 100},
        {
            "PC_MEASURED_IDLE_W": 100,
            "PC_MEASURED_SLEEP_W": 5,
            "PC_SAVABLE_HOURS": 2,
            "OCCURRENCE_DAYS": 30,
        },
    )
    assert any("월 전기사용량" in w for w in r["warnings"])


def test_measurement_required_standby_needs_measured_power():
    sol = {
        "solution_id": "SOL_PC_005",
        "waste_code": "PC_OFF_STANDBY_LEAK",
        "formula_id": "F_STANDBY_CUTOFF",
        "calculation_available": True,
        "requires_measurement": True,
    }
    r = calculate_solution_saving(
        sol,
        {},
        {"STANDBY_COUNT": 10, "CUTOFF_HOURS": 8, "OCCURRENCE_DAYS": 30, "SHUTDOWN_ALLOWED": True},
    )
    assert r["calculation_status"] == "NEEDS_INPUT"
    assert "STANDBY_W" in r["missing_inputs"]


def test_calculate_all_does_not_sum_overlap():
    results = calculate_all_solutions(
        [PC_SOL, {**PC_SOL, "solution_id": "SOL_PC_001"}],
        {"Q01": 100, "Q03": "EMPTY_31_50"},
        {
            "PC_MEASURED_IDLE_W": 100,
            "PC_MEASURED_SLEEP_W": 5,
            "PC_SAVABLE_HOURS": 2,
            "OCCURRENCE_DAYS": 30,
        },
    )
    assert len(results) == 2
    assert results[0]["overlap_group"] == "PC_IDLE_ENERGY"
    assert results[1]["overlap_group"] == "PC_IDLE_ENERGY"
    assert "total_energy_saving_kwh" not in results[0]
