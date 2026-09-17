
"""PC방 AI 에너지 코치 Ranking Engine.

역할:
- 이미 진단된 solution들을 우선순위화한다.
- Risk / Solution / Calculation / RAG 결과만 사용한다.
- 새로운 위험 판단이나 절감량 생성은 하지 않는다.

주의:
- internal_priority_score는 서비스 내부 MVP 점수이다.
- 공공기관 공식 등급이나 에너지 효율등급이 아니다.
- 절감량(kWh)은 주요 점수가 아니라 동점 해소용으로만 사용한다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


RANKING_VERSION = "v1"

# ============================================================
# 내부 Ranking Weight
# ============================================================

RISK_SCORE_CAP = 10.0
RISK_WEIGHT_MAX = 50.0

RAG_GROUNDED_POINTS = 15.0

SOLUTION_TYPE_POINTS = {
    "ACTION": 15.0,
    "CHECK": 10.0,
    "MEASURE": 7.0,
}

CALCULATION_STATUS_POINTS = {
    "CALCULATED": 10.0,
    "ESTIMATED": 8.0,
    "NEEDS_INPUT": 4.0,
    "NOT_CALCULABLE": 5.0,
    "FORMULA_NOT_FOUND": 0.0,
    None: 0.0,
}

CONFIDENCE_POINTS = {
    "HIGH": 5.0,
    "MEDIUM": 3.0,
    "LOW": 1.0,
    None: 0.0,
}

CONFIRMATION_PENALTY = 8.0
MEASUREMENT_PENALTY = 4.0


class RankingError(ValueError):
    pass


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _calculation_map(
    calculation_results: Optional[Sequence[Dict[str, Any]]]
) -> Dict[str, Dict[str, Any]]:

    result = {}

    for row in calculation_results or []:
        solution_id = row.get("solution_id")

        if solution_id:
            result[str(solution_id)] = dict(row)

    return result


def _merge_candidate(
    solution: Dict[str, Any],
    calculation: Optional[Dict[str, Any]],
) -> Dict[str, Any]:

    merged = dict(solution)

    if calculation:
        merged.update(calculation)

        # calculation 결과에는 설명 필드가 없을 수 있으므로
        # solution 결과에서 유지
        for key in (
            "solution_name",
            "solution_type",
            "risk_score",
            "risk_level",
            "needs_confirmation",
            "confirmation_required",
            "requires_measurement",
            "rag_grounded",
            "rag_evidence_count",
            "rag_evidence",
            "rag_query",
        ):
            if key not in merged or merged.get(key) is None:
                merged[key] = solution.get(key)

    return merged


def _risk_points(risk_score: Any) -> float:

    score = max(
        0.0,
        _safe_float(risk_score)
    )

    capped = min(
        score,
        RISK_SCORE_CAP
    )

    return round(
        (capped / RISK_SCORE_CAP)
        * RISK_WEIGHT_MAX,
        4,
    )


def _next_step(candidate: Mapping[str, Any]) -> str:
    """
    Ranking 결과를 UI에서 어떻게 표현할지 결정.
    """

    if (
        candidate.get("confirmation_required")
        or candidate.get("needs_confirmation")
    ):
        return "CONFIRM_FIRST"

    if candidate.get("requires_measurement"):
        return "MEASURE_FIRST"

    if candidate.get("calculation_status") == "NEEDS_INPUT":
        return "COLLECT_INPUT_FIRST"

    solution_type = str(
        candidate.get("solution_type") or ""
    ).upper()

    if solution_type == "CHECK":
        return "CHECK_FIRST"

    if solution_type == "MEASURE":
        return "MEASURE_FIRST"

    return "ACTION"


def _estimated_saving_tiebreak(
    candidate: Mapping[str, Any]
) -> float:
    """
    절감량은 Ranking 점수에 직접 합산하지 않는다.

    동일한 우선순위 후보끼리의
    tie-break 용도로만 사용한다.
    """

    lo = candidate.get(
        "energy_saving_kwh_min"
    )

    hi = candidate.get(
        "energy_saving_kwh_max"
    )

    value = (
        lo
        if lo is not None
        else hi
    )

    return max(
        0.0,
        _safe_float(value)
    )


def _score_candidate(
    candidate: Mapping[str, Any]
) -> Tuple[
    float,
    Dict[str, float],
    List[str],
]:

    components = {}
    reasons = []

    # --------------------------------------------------------
    # 1. Risk
    # --------------------------------------------------------

    risk_score = max(
        0.0,
        _safe_float(
            candidate.get("risk_score")
        ),
    )

    components["risk"] = _risk_points(
        risk_score
    )

    reasons.append(
        f"내부 위험점수 {risk_score:g}"
    )

    # --------------------------------------------------------
    # 2. RAG 공식 근거
    # --------------------------------------------------------

    rag_grounded = bool(
        candidate.get("rag_grounded")
    )

    components["rag_grounding"] = (
        RAG_GROUNDED_POINTS
        if rag_grounded
        else 0.0
    )

    if rag_grounded:
        reasons.append(
            "공식 근거 RAG 연결됨"
        )

    # --------------------------------------------------------
    # 3. 실행 가능성
    # --------------------------------------------------------

    solution_type = str(
        candidate.get("solution_type")
        or ""
    ).upper()

    components["actionability"] = (
        SOLUTION_TYPE_POINTS.get(
            solution_type,
            0.0,
        )
    )

    if solution_type:
        reasons.append(
            f"솔루션 유형 {solution_type}"
        )

    # --------------------------------------------------------
    # 4. Calculation 상태
    # --------------------------------------------------------

    calc_status = candidate.get(
        "calculation_status"
    )

    components["calculation_readiness"] = (
        CALCULATION_STATUS_POINTS.get(
            calc_status,
            0.0,
        )
    )

    if calc_status:
        reasons.append(
            f"계산 상태 {calc_status}"
        )

    # --------------------------------------------------------
    # 5. Calculation 신뢰도
    # --------------------------------------------------------

    confidence = candidate.get(
        "confidence"
    )

    # MVP에서는 계산 신뢰도를
    # Ranking 및 사용자 출력에서 사용하지 않음

    # --------------------------------------------------------
    # 6. 확인 필요 패널티
    # --------------------------------------------------------

    confirmation_required = bool(
        candidate.get("confirmation_required")
        or candidate.get("needs_confirmation")
    )

    components["confirmation_penalty"] = (
        -CONFIRMATION_PENALTY
        if confirmation_required
        else 0.0
    )

    if confirmation_required:
        reasons.append(
            "실행 전 상태 확인 필요"
        )

    # --------------------------------------------------------
    # 7. 계측 필요 패널티
    # --------------------------------------------------------

    requires_measurement = bool(
        candidate.get("requires_measurement")
    )

    components["measurement_penalty"] = (
        -MEASUREMENT_PENALTY
        if requires_measurement
        else 0.0
    )

    if requires_measurement:
        reasons.append(
            "현장 측정 필요"
        )

    score = round(
        sum(components.values()),
        4,
    )

    return (
        score,
        components,
        reasons,
    )


def _candidate_is_eligible(
    candidate: Mapping[str, Any],
    require_rag: bool,
):

    solution_id = candidate.get(
        "solution_id"
    )

    if not solution_id:
        return (
            False,
            "solution_id missing",
        )

    # 공식근거 없는 추천은 최종 Top-3에서 제외
    if (
        require_rag
        and not candidate.get(
            "rag_grounded"
        )
    ):
        return (
            False,
            "RAG evidence missing",
        )

    # 계산 가능하다고 정의했는데
    # formula 자체가 없는 경우 시스템 오류로 간주
    if (
        candidate.get(
            "calculation_available"
        )
        and candidate.get(
            "calculation_status"
        )
        == "FORMULA_NOT_FOUND"
    ):
        return (
            False,
            "calculation formula missing",
        )

    return True, None


def rank_solutions(
    grounded_solutions: Sequence[
        Dict[str, Any]
    ],
    calculation_results: Optional[
        Sequence[Dict[str, Any]]
    ] = None,
    *,
    top_n: int = 3,
    require_rag: bool = True,
    deduplicate_overlap: bool = True,
) -> Dict[str, Any]:

    if top_n <= 0:
        raise RankingError(
            "top_n must be positive"
        )

    calc_by_solution = (
        _calculation_map(
            calculation_results
        )
    )

    scored = []
    excluded = []

    # ========================================================
    # 후보 생성
    # ========================================================

    for solution in grounded_solutions:

        solution_id = solution.get(
            "solution_id"
        )

        candidate = _merge_candidate(
            solution,
            calc_by_solution.get(
                str(solution_id)
            ),
        )

        eligible, reason = (
            _candidate_is_eligible(
                candidate,
                require_rag=require_rag,
            )
        )

        if not eligible:

            excluded.append({
                "solution_id":
                    solution_id,

                "waste_code":
                    candidate.get(
                        "waste_code"
                    ),

                "reason":
                    reason,
            })

            continue

        (
            score,
            components,
            reasons,
        ) = _score_candidate(
            candidate
        )

        candidate[
            "internal_priority_score"
        ] = score

        candidate[
            "ranking_components"
        ] = components

        candidate[
            "ranking_reasons"
        ] = reasons

        candidate[
            "next_step"
        ] = _next_step(
            candidate
        )

        candidate[
            "saving_tiebreak_kwh"
        ] = _estimated_saving_tiebreak(
            candidate
        )

        scored.append(
            candidate
        )

    # ========================================================
    # Ranking
    # ========================================================

    calc_status_rank = {
        "CALCULATED": 5,
        "ESTIMATED": 4,
        "NOT_CALCULABLE": 3,
        "NEEDS_INPUT": 2,
        "FORMULA_NOT_FOUND": 0,
        None: 0,
    }

    scored.sort(
        key=lambda x: (
            -_safe_float(
                x.get(
                    "internal_priority_score"
                )
            ),

            -_safe_float(
                x.get(
                    "risk_score"
                )
            ),

            -calc_status_rank.get(
                x.get(
                    "calculation_status"
                ),
                0,
            ),

            # 절감량은 tie-break만
            -_safe_float(
                x.get(
                    "saving_tiebreak_kwh"
                )
            ),

            str(
                x.get(
                    "solution_id"
                )
                or ""
            ),
        )
    )

    # ========================================================
    # Overlap 제거
    # ========================================================

    selected = []

    suppressed_overlaps = []

    seen_overlap_groups = {}

    for candidate in scored:

        if len(selected) >= top_n:
            break

        overlap_group = (
            candidate.get(
                "overlap_group"
            )
        )

        if (
            deduplicate_overlap
            and overlap_group
        ):

            if (
                overlap_group
                in seen_overlap_groups
            ):

                suppressed_overlaps.append({
                    "solution_id":
                        candidate.get(
                            "solution_id"
                        ),

                    "waste_code":
                        candidate.get(
                            "waste_code"
                        ),

                    "overlap_group":
                        overlap_group,

                    "suppressed_by_solution_id":
                        seen_overlap_groups[
                            overlap_group
                        ],
                })

                continue

            seen_overlap_groups[
                overlap_group
            ] = str(
                candidate.get(
                    "solution_id"
                )
            )

        selected.append(
            candidate
        )

    # ========================================================
    # 최종 순위 부여
    # ========================================================

    for rank, candidate in enumerate(
        selected,
        start=1,
    ):

        candidate["rank"] = rank

    return {
        "ranking_version":
            RANKING_VERSION,

        "top_n_requested":
            top_n,

        "candidate_count":
            len(
                grounded_solutions
            ),

        "eligible_count":
            len(scored),

        "selected_count":
            len(selected),

        "top_recommendations":
            selected,

        "suppressed_overlaps":
            suppressed_overlaps,

        "excluded":
            excluded,

        "score_notice":
            (
                "internal MVP priority score; "
                "not an official energy grade"
            ),
    }
