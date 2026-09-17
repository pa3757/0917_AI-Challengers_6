
from src.ranking_engine import rank_solutions


def solution(
    solution_id,
    waste_code,
    risk_score,
    **kwargs,
):

    data = {
        "solution_id": solution_id,
        "waste_code": waste_code,
        "solution_name": solution_id,
        "solution_type": "ACTION",
        "risk_score": risk_score,
        "risk_level":
            "HIGH"
            if risk_score >= 6
            else "MEDIUM",

        "calculation_available": True,
        "requires_measurement": False,
        "needs_confirmation": False,

        "rag_grounded": True,
        "rag_evidence_count": 1,
        "rag_evidence": [
            {
                "knowledge_id":
                    f"KB_{waste_code}"
            }
        ],
    }

    data.update(kwargs)

    return data


def calc(
    solution_id,
    waste_code,
    status="ESTIMATED",
    overlap_group=None,
    saving=10,
    confidence="MEDIUM",
):

    return {
        "solution_id": solution_id,
        "waste_code": waste_code,

        "calculation_status":
            status,

        "energy_saving_kwh_min":
            saving,

        "energy_saving_kwh_max":
            saving,

        "cost_saving_krw_min":
            None,

        "cost_saving_krw_max":
            None,

        "confidence":
            confidence,

        "overlap_group":
            overlap_group,
    }


def test_high_risk_first():

    grounded = [
        solution(
            "S1",
            "W1",
            7,
        ),
        solution(
            "S2",
            "W2",
            3,
        ),
    ]

    calculation = [
        calc(
            "S1",
            "W1",
        ),
        calc(
            "S2",
            "W2",
        ),
    ]

    result = rank_solutions(
        grounded,
        calculation,
        top_n=2,
    )

    assert (
        result[
            "top_recommendations"
        ][0]["solution_id"]
        == "S1"
    )


def test_missing_rag_excluded():

    grounded = [
        solution(
            "S1",
            "W1",
            8,
            rag_grounded=False,
            rag_evidence_count=0,
            rag_evidence=[],
        ),

        solution(
            "S2",
            "W2",
            4,
        ),
    ]

    calculation = [
        calc("S1", "W1"),
        calc("S2", "W2"),
    ]

    result = rank_solutions(
        grounded,
        calculation,
    )

    ids = [
        x["solution_id"]
        for x in result[
            "top_recommendations"
        ]
    ]

    assert "S1" not in ids
    assert "S2" in ids


def test_confirmation_penalty():

    grounded = [
        solution(
            "S1",
            "W1",
            5,
        ),

        solution(
            "S2",
            "W2",
            5,
            needs_confirmation=True,
            confirmation_required=True,
            requires_measurement=True,
        ),
    ]

    calculation = [
        calc("S1", "W1"),
        calc("S2", "W2"),
    ]

    result = rank_solutions(
        grounded,
        calculation,
        top_n=2,
    )

    top = result[
        "top_recommendations"
    ]

    assert (
        top[0]["solution_id"]
        == "S1"
    )

    assert (
        top[1]["next_step"]
        == "CONFIRM_FIRST"
    )


def test_overlap_removed():

    grounded = [
        solution(
            "S1",
            "W1",
            7,
        ),

        solution(
            "S2",
            "W2",
            6,
        ),

        solution(
            "S3",
            "W3",
            5,
        ),
    ]

    calculation = [
        calc(
            "S1",
            "W1",
            overlap_group=
                "PC_IDLE_ENERGY",
        ),

        calc(
            "S2",
            "W2",
            overlap_group=
                "PC_IDLE_ENERGY",
        ),

        calc(
            "S3",
            "W3",
        ),
    ]

    result = rank_solutions(
        grounded,
        calculation,
        top_n=3,
    )

    ids = [
        x["solution_id"]
        for x in result[
            "top_recommendations"
        ]
    ]

    assert ids == [
        "S1",
        "S3",
    ]


def test_saving_is_only_tiebreak():

    grounded = [
        solution(
            "HIGH_RISK",
            "W1",
            7,
        ),

        solution(
            "BIG_SAVING",
            "W2",
            3,
        ),
    ]

    calculation = [
        calc(
            "HIGH_RISK",
            "W1",
            saving=1,
        ),

        calc(
            "BIG_SAVING",
            "W2",
            saving=9999,
        ),
    ]

    result = rank_solutions(
        grounded,
        calculation,
        top_n=2,
    )

    assert (
        result[
            "top_recommendations"
        ][0]["solution_id"]
        == "HIGH_RISK"
    )


def test_formula_error_excluded():

    grounded = [
        solution(
            "S1",
            "W1",
            8,
            calculation_available=True,
        )
    ]

    calculation = [
        calc(
            "S1",
            "W1",
            status="FORMULA_NOT_FOUND",
        )
    ]

    result = rank_solutions(
        grounded,
        calculation,
    )

    assert (
        result[
            "top_recommendations"
        ]
        == []
    )
