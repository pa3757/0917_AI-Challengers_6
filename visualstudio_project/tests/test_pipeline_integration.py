from src.rule_engine import evaluate_risks
from src.solution_engine import recommend_solutions
from src.calculator import calculate_all_solutions


def test_survey_to_risk_to_solution_to_calculation_pipeline():
    answers = {
        "Q01": 100,
        "Q02": 24,
        "Q03": "EMPTY_31_50",
        "Q05": "BOTH_ON",
        "Q06": "OVER_30_MIN",
    }
    risks = evaluate_risks(answers)
    solutions = recommend_solutions(risks)
    pc_solutions = [s for s in solutions if s["solution_id"] in {"SOL_PC_001", "SOL_PC_003"}]
    assert pc_solutions

    calculated = calculate_all_solutions(
        pc_solutions,
        answers,
        {
            "PC_MEASURED_IDLE_W": 100,
            "PC_MEASURED_SLEEP_W": 5,
            "PC_SAVABLE_HOURS": 2,
            "OCCURRENCE_DAYS": 30,
        },
    )
    assert all(r["calculation_status"] == "ESTIMATED" for r in calculated)
    assert all(r["energy_saving_kwh_min"] is not None for r in calculated)
    assert all(r["overlap_group"] == "PC_IDLE_ENERGY" for r in calculated)
