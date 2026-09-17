
"""
MVP Calculation Engine

원칙
1. 기존 Calculation Engine 계산값 우선
2. 계산 불가/입력 부족 시 MVP fallback 추정
3. 사용자 화면에는 모든 추천에 kWh 범위 제공
4. 모든 kWh 결과에 130원/kWh 적용
5. confidence는 사용자에게 사용하지 않음

MVP fallback은 공식 절감률이 아니라
서비스 내부 참고 시나리오이다.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .calculator import calculate_all_solutions


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REFERENCE_DB_PATH = (
    PROJECT_ROOT
    / "data"
    / "05_calculation"
    / "PC방_Calculation_Reference_DB.csv"
)


# =========================================================
# MVP 기본값
# =========================================================

REFERENCE_KRW_PER_KWH = 130.0

DEFAULT_PC_COUNT = 50
DEFAULT_BUSINESS_HOURS = 16.0
DEFAULT_OPERATING_DAYS = 30

# DB/사용자값으로 PC 기준 전력을 못 구했을 때만 사용
MVP_PC_REFERENCE_W = 100.0
MVP_MONITOR_REFERENCE_W = 25.0


# =========================================================
# waste_code별 MVP 절감 잠재율
#
# 월 기준 에너지 proxy 중 해당 낭비요인으로
# 개선 가능할 수 있는 범위를 뜻함.
#
# 공식 절감률이 아니라 MVP 내부 추정치.
# =========================================================

MVP_SAVING_RATE_BANDS = {

    "PC_IDLE_ON":
        (0.020, 0.050),

    "MONITOR_IDLE_ON":
        (0.005, 0.015),

    "PC_IDLE_WINDOW_LEAK":
        (0.010, 0.030),

    "PC_UPDATE_IDLE":
        (0.003, 0.010),

    "PC_OFF_STANDBY_LEAK":
        (0.001, 0.005),

    "PERIPHERAL_IDLE_POWER":
        (0.002, 0.008),

    "HVAC_EXCESS_COOLING":
        (0.020, 0.060),

    "HVAC_TEMPERATURE_UNCHECKED":
        (0.010, 0.030),

    "HVAC_FILTER_MAINTENANCE":
        (0.005, 0.020),

    "HVAC_OUTDOOR_HEAT_RECIRCULATION":
        (0.005, 0.020),

    "LOW_OCCUPANCY_ZONE_OPERATION":
        (0.015, 0.050),

    "HIDDEN_BASELOAD_RISK":
        (0.010, 0.040),

    "ENERGY_MONITORING_ABSENT":
        (0.003, 0.015),

    "REFRIG_DOOR_HEATER_ALWAYS_ON":
        (0.003, 0.012),

    "REFRIG_DEFROST_CONTROL":
        (0.002, 0.010),
}


# =========================================================
# Utilities
# =========================================================

def _float(
    value: Any,
    default: Optional[float] = None,
) -> Optional[float]:

    try:

        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def _json(value: Any):

    if not value:
        return {}

    try:
        return json.loads(value)

    except Exception:
        return {}


# =========================================================
# Reference DB 로드
# =========================================================

def _load_reference_rows():

    rows = []

    if not REFERENCE_DB_PATH.exists():
        return rows

    with REFERENCE_DB_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        for raw in reader:

            row = dict(raw)

            row["value_min"] = _float(
                row.get("value_min")
            )

            row["value_max"] = _float(
                row.get("value_max")
            )

            row["applicability"] = _json(
                row.get("applicability")
            )

            rows.append(row)

    return rows


# =========================================================
# DB에서 실제 계산 가능한 W 값 탐색
# =========================================================

def _find_reference_power(
    rows,
    equipment_keywords,
    state_keywords=None,
):

    candidates = []

    equipment_keywords = [
        x.lower()
        for x in equipment_keywords
    ]

    state_keywords = [
        x.lower()
        for x in (
            state_keywords or []
        )
    ]

    for row in rows:

        equipment = str(
            row.get("equipment") or ""
        ).lower()

        parameter = str(
            row.get("parameter") or ""
        ).lower()

        state = str(
            row.get("state") or ""
        ).lower()

        unit = str(
            row.get("unit") or ""
        ).lower()

        ref_type = str(
            row.get("reference_type") or ""
        ).lower()

        applicability = (
            row.get("applicability")
            or {}
        )

        # 설비 매칭
        if not any(
            keyword in equipment
            for keyword
            in equipment_keywords
        ):
            continue

        # W 계열만
        if unit != "w":
            continue

        # 소비전력 관련 항목만
        if not (
            "electric" in parameter
            or "power" in parameter
            or "input" in parameter
        ):
            continue

        # 규제 상한을 실제 전력으로 사용 금지
        if ref_type in {
            "regulatory_limit",
            "regulatory_allowance",
        }:
            continue

        if (
            applicability
            and applicability.get(
                "calculation_eligible"
            )
            is False
        ):
            continue

        if state_keywords:

            if not any(
                keyword in state
                for keyword
                in state_keywords
            ):
                continue

        lo = row.get("value_min")
        hi = row.get("value_max")

        if lo is None and hi is None:
            continue

        if lo is None:
            lo = hi

        if hi is None:
            hi = lo

        value = (
            float(lo)
            + float(hi)
        ) / 2

        if value <= 0:
            continue

        candidates.append({
            "value": value,
            "reference_id":
                row.get("reference_id"),
        })

    if not candidates:
        return None

    # 극단값 방지용 중앙값 근사
    values = sorted(
        x["value"]
        for x in candidates
    )

    value = values[
        len(values) // 2
    ]

    return value


# =========================================================
# PC 기준전력
# =========================================================

def resolve_reference_pc_w(
    user_measurements,
    reference_rows,
):

    m = user_measurements or {}

    # 1. 사용자 실측
    for key in [
        "PC_MEASURED_IDLE_W",
        "PC_MEASURED_ACTIVE_W",
    ]:

        value = _float(
            m.get(key)
        )

        if value is not None and value > 0:

            return (
                value,
                "USER_OR_MEASURED"
            )

    # 2. Calculation Reference DB
    db_value = _find_reference_power(
        reference_rows,
        equipment_keywords=[
            "desktop",
            "computer",
            "pc",
        ],
        state_keywords=[
            "idle",
            "active",
            "on",
        ],
    )

    if db_value is not None:

        return (
            db_value,
            "CALCULATION_REFERENCE_DB"
        )

    # 3. MVP fallback
    return (
        MVP_PC_REFERENCE_W,
        "MVP_REFERENCE_SCENARIO"
    )


def resolve_reference_monitor_w(
    user_measurements,
    reference_rows,
):

    m = user_measurements or {}

    for key in [
        "MONITOR_ON_W",
        "MONITOR_MEASURED_ON_W",
    ]:

        value = _float(
            m.get(key)
        )

        if value is not None and value > 0:

            return (
                value,
                "USER_OR_MEASURED"
            )

    db_value = _find_reference_power(
        reference_rows,
        equipment_keywords=[
            "monitor",
            "display",
        ],
        state_keywords=[
            "on",
            "active",
        ],
    )

    if db_value is not None:

        return (
            db_value,
            "CALCULATION_REFERENCE_DB"
        )

    return (
        MVP_MONITOR_REFERENCE_W,
        "MVP_REFERENCE_SCENARIO"
    )


# =========================================================
# Q03 빈 좌석률
# =========================================================

EMPTY_RATE_MAP = {

    "EMPTY_0_10":
        (0.00, 0.10),

    "EMPTY_11_30":
        (0.11, 0.30),

    "EMPTY_31_50":
        (0.31, 0.50),

    "EMPTY_51_PLUS":
        (0.51, 0.70),

    "UNKNOWN":
        (0.20, 0.40),
}


def empty_rate_midpoint(
    answer,
):

    lo, hi = EMPTY_RATE_MAP.get(
        answer,
        (0.20, 0.40),
    )

    return (
        lo + hi
    ) / 2


# =========================================================
# PC방 규모 기반 월 전력 proxy
# =========================================================

def estimate_monthly_energy_proxy(
    answers: Dict[str, Any],
    user_measurements=None,
):

    reference_rows = (
        _load_reference_rows()
    )

    pc_count = _float(
        answers.get("Q01"),
        DEFAULT_PC_COUNT,
    )

    business_hours = _float(
        answers.get("Q02"),
        DEFAULT_BUSINESS_HOURS,
    )

    if pc_count is None or pc_count <= 0:
        pc_count = DEFAULT_PC_COUNT

    if (
        business_hours is None
        or business_hours <= 0
    ):
        business_hours = (
            DEFAULT_BUSINESS_HOURS
        )

    pc_w, pc_source = (
        resolve_reference_pc_w(
            user_measurements,
            reference_rows,
        )
    )

    monitor_w, monitor_source = (
        resolve_reference_monitor_w(
            user_measurements,
            reference_rows,
        )
    )

    # PC + Monitor 기준 사업장 규모 proxy
    base_w = (
        pc_w
        + monitor_w
    )

    monthly_proxy = (
        base_w
        * pc_count
        * business_hours
        * DEFAULT_OPERATING_DAYS
        / 1000
    )

    # 매우 작게 나오는 경우 방지
    monthly_proxy = max(
        monthly_proxy,
        500.0,
    )

    return {
        "monthly_energy_proxy_kwh":
            monthly_proxy,

        "pc_count":
            pc_count,

        "business_hours":
            business_hours,

        "pc_reference_w":
            pc_w,

        "monitor_reference_w":
            monitor_w,

        "pc_reference_source":
            pc_source,

        "monitor_reference_source":
            monitor_source,

        "empty_rate_mid":
            empty_rate_midpoint(
                answers.get("Q03")
            ),
    }


# =========================================================
# Risk multiplier
# =========================================================

def _risk_multiplier(
    risk_score,
):

    score = _float(
        risk_score,
        3,
    )

    if score >= 9:
        return 1.15

    if score >= 6:
        return 1.00

    if score >= 3:
        return 0.85

    return 0.70


# =========================================================
# 모든 None을 제거하는 MVP fallback
# =========================================================

def fill_mvp_estimates(
    calculation_results:
        Sequence[Dict[str, Any]],

    solutions:
        Sequence[Dict[str, Any]],

    answers:
        Dict[str, Any],

    user_measurements=None,

    rate_per_kwh:
        float = REFERENCE_KRW_PER_KWH,
):

    proxy = (
        estimate_monthly_energy_proxy(
            answers,
            user_measurements,
        )
    )

    baseline_kwh = (
        proxy[
            "monthly_energy_proxy_kwh"
        ]
    )

    solution_map = {
        str(x.get("solution_id")): x
        for x in solutions
    }

    results = []

    for raw in calculation_results:

        item = dict(raw)

        solution = solution_map.get(
            str(
                item.get("solution_id")
            ),
            {},
        )

        waste_code = (
            item.get("waste_code")
            or solution.get(
                "waste_code"
            )
        )

        risk_score = (
            solution.get("risk_score")
            or item.get("risk_score")
            or 3
        )

        kwh_min = _float(
            item.get(
                "energy_saving_kwh_min"
            )
        )

        kwh_max = _float(
            item.get(
                "energy_saving_kwh_max"
            )
        )

        # =================================================
        # A. 기존 Formula 계산값 존재
        # =================================================

        if (
            kwh_min is not None
            or kwh_max is not None
        ):

            if kwh_min is None:
                kwh_min = kwh_max

            if kwh_max is None:
                kwh_max = kwh_min

            kwh_min = max(
                0.0,
                float(kwh_min),
            )

            kwh_max = max(
                kwh_min,
                float(kwh_max),
            )

            method = (
                "FORMULA_CALCULATION"
            )

            display_basis = (
                "기존 Calculation DB/Formula 기반 계산"
            )

        # =================================================
        # B. 기존 엔진이 계산 못함
        # =================================================

        else:

            rate_min, rate_max = (
                MVP_SAVING_RATE_BANDS.get(
                    waste_code,
                    (0.003, 0.010),
                )
            )

            multiplier = (
                _risk_multiplier(
                    risk_score
                )
            )

            adjusted_min = (
                rate_min
                * multiplier
            )

            adjusted_max = (
                rate_max
                * multiplier
            )

            kwh_min = (
                baseline_kwh
                * adjusted_min
            )

            kwh_max = (
                baseline_kwh
                * adjusted_max
            )

            # 최소 1kWh 이상 표시
            kwh_min = max(
                1.0,
                kwh_min,
            )

            kwh_max = max(
                kwh_min,
                kwh_max,
            )

            method = (
                "MVP_REFERENCE_ESTIMATE"
            )

            display_basis = (
                "PC 수·영업시간·Calculation DB "
                "기준전력과 내부 절감 시나리오를 "
                "이용한 MVP 참고 추정"
            )

            item[
                "calculation_status"
            ] = "ESTIMATED"

            item[
                "mvp_saving_rate_min"
            ] = adjusted_min

            item[
                "mvp_saving_rate_max"
            ] = adjusted_max

        # 소수 첫째자리
        kwh_min = round(
            kwh_min,
            1,
        )

        kwh_max = round(
            kwh_max,
            1,
        )

        item[
            "energy_saving_kwh_min"
        ] = kwh_min

        item[
            "energy_saving_kwh_max"
        ] = kwh_max

        # =================================================
        # 비용도 무조건 생성
        # =================================================

        cost_min = (
            kwh_min
            * rate_per_kwh
        )

        cost_max = (
            kwh_max
            * rate_per_kwh
        )

        # 100원 단위
        item[
            "cost_saving_krw_min"
        ] = round(
            cost_min / 100
        ) * 100

        item[
            "cost_saving_krw_max"
        ] = round(
            cost_max / 100
        ) * 100

        item[
            "energy_estimate_method"
        ] = method

        item[
            "energy_estimate_basis"
        ] = display_basis

        item[
            "reference_rate_krw_per_kwh"
        ] = rate_per_kwh

        item[
            "monthly_energy_proxy_kwh"
        ] = round(
            baseline_kwh,
            1,
        )

        item[
            "cost_estimate_note"
        ] = (
            f"예상 절감전력량 × "
            f"{rate_per_kwh:,.0f}원/kWh"
        )

        # 사용자가 confidence 표시를 원하지 않음
        item.pop(
            "confidence",
            None,
        )

        item.pop(
            "confidence_summary",
            None,
        )

        item.pop(
            "confidence_reasons",
            None,
        )

        item.pop(
            "input_provenance",
            None,
        )

        results.append(item)

    return results


# =========================================================
# 최종 Wrapper
# =========================================================

def calculate_all_solutions_mvp(
    solutions,
    answers,
    user_measurements=None,
    *,
    rate_per_kwh=REFERENCE_KRW_PER_KWH,
):

    # 기존 정식 Calculation Engine 먼저 실행
    raw_results = (
        calculate_all_solutions(
            solutions,
            answers,
            user_measurements=
                user_measurements,
        )
    )

    # 빈 값은 MVP fallback으로 채움
    return fill_mvp_estimates(
        raw_results,
        solutions,
        answers,
        user_measurements,
        rate_per_kwh=
            rate_per_kwh,
    )
