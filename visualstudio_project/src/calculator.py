"""Deterministic energy/cost calculation engine for the PC-room MVP.

Important constraints:
- No LLM-generated numeric values.
- CSV formula strings are documentation; they are never eval()'d.
- Regulatory limits are never treated as actual consumption.
- Per-solution savings are not automatically summed because overlap can exist.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .calculation_input_resolver import (
    DEFAULT_FORMULA_PATH,
    DEFAULT_REFERENCE_PATH,
    load_formula_db,
    load_reference_db,
    resolve_formula_inputs,
    resolve_survey_inputs,
)


SOLUTION_CONTEXT = {
    "SOL_PC_001": {"PC_BASE_STATE": "idle", "PC_TARGET_STATE": "sleep"},
    "SOL_PC_002": {"MONITOR_TARGET_STATE": "sleep"},
    "SOL_PC_003": {"PC_BASE_STATE": "idle", "PC_TARGET_STATE": "sleep"},
    # Update work can keep the machine in an active state; active W must be measured/model-specific.
    "SOL_PC_004": {"PC_BASE_STATE": "active", "PC_TARGET_STATE": "sleep"},
}

OVERLAP_GROUP = {
    "SOL_PC_001": "PC_IDLE_ENERGY",
    "SOL_PC_003": "PC_IDLE_ENERGY",
    "SOL_PC_004": "PC_UPDATE_ENERGY",
    "SOL_PC_005": "PERIPHERAL_STANDBY",
    "SOL_PC_006": "PERIPHERAL_STANDBY",
}


class CalculationError(ValueError):
    pass


def _numeric_interval(record: Dict[str, Any], name: str) -> Tuple[Optional[float], Optional[float]]:
    if record is None:
        raise CalculationError(f"필수 입력 누락: {name}")
    lo = record.get("value_min")
    hi = record.get("value_max")
    if lo is None and hi is None:
        raise CalculationError(f"숫자 입력이 아님: {name}")
    lo = float(lo) if lo is not None else None
    hi = float(hi) if hi is not None else None
    if lo is not None and not math.isfinite(lo):
        raise CalculationError(f"유효하지 않은 숫자: {name}")
    if hi is not None and not math.isfinite(hi):
        raise CalculationError(f"유효하지 않은 숫자: {name}")
    return lo, hi


def _point(record: Dict[str, Any], name: str) -> float:
    lo, hi = _numeric_interval(record, name)
    if lo is None or hi is None or lo != hi:
        raise CalculationError(f"점값이 필요한 입력에 범위/미확정 값이 사용됨: {name}")
    return lo


def _multiply_nonnegative_intervals(intervals: Iterable[Tuple[Optional[float], Optional[float]]]) -> Tuple[Optional[float], Optional[float]]:
    min_product: Optional[float] = 1.0
    max_product: Optional[float] = 1.0
    for lo, hi in intervals:
        if lo is None:
            min_product = None
        elif lo < 0:
            raise CalculationError("비음수 입력이 필요한 곱셈에 음수가 포함됨")
        elif min_product is not None:
            min_product *= lo

        if hi is None:
            max_product = None
        elif hi < 0:
            raise CalculationError("비음수 입력이 필요한 곱셈에 음수가 포함됨")
        elif max_product is not None:
            max_product *= hi
    return min_product, max_product


def _difference_interval(base: Tuple[Optional[float], Optional[float]], target: Tuple[Optional[float], Optional[float]]) -> Tuple[Optional[float], Optional[float]]:
    base_lo, base_hi = base
    target_lo, target_hi = target
    lo = base_lo - target_hi if base_lo is not None and target_hi is not None else None
    hi = base_hi - target_lo if base_hi is not None and target_lo is not None else None
    return lo, hi


def _calculate_state_change(
    resolved: Dict[str, Dict[str, Any]],
    base_key: str,
    target_key: str,
    count_key: str,
    hours_key: str,
    days_key: str,
) -> Tuple[Optional[float], Optional[float], List[str]]:
    warnings: List[str] = []
    delta = _difference_interval(_numeric_interval(resolved[base_key], base_key), _numeric_interval(resolved[target_key], target_key))
    if delta[0] is not None and delta[0] < 0:
        warnings.append(f"{base_key} - {target_key}의 최소값이 음수입니다. 절감이 아니라 증가 가능성이 있습니다.")
    if delta[1] is not None and delta[1] < 0:
        warnings.append(f"{base_key} - {target_key}의 최대값이 음수입니다. 절감이 아니라 증가입니다.")

    # The product helper expects nonnegative intervals. Preserve negative deltas as a special case.
    if (delta[0] is not None and delta[0] < 0) or (delta[1] is not None and delta[1] < 0):
        # For current MVP formulas, other terms are nonnegative; endpoint multiplication is sufficient.
        count = _numeric_interval(resolved[count_key], count_key)
        hours = _numeric_interval(resolved[hours_key], hours_key)
        days = _numeric_interval(resolved[days_key], days_key)
        endpoints = []
        for d in delta:
            for c in count:
                for h in hours:
                    for day in days:
                        if None not in (d, c, h, day):
                            endpoints.append(d * c * h * day / 1000.0)
        return (min(endpoints) if endpoints else None, max(endpoints) if endpoints else None, warnings)

    lo, hi = _multiply_nonnegative_intervals(
        [delta, _numeric_interval(resolved[count_key], count_key), _numeric_interval(resolved[hours_key], hours_key), _numeric_interval(resolved[days_key], days_key)]
    )
    return (lo / 1000.0 if lo is not None else None, hi / 1000.0 if hi is not None else None, warnings)


def _dispatch_energy_formula(formula_id: str, resolved: Dict[str, Dict[str, Any]]) -> Tuple[Optional[float], Optional[float], List[str]]:
    if formula_id == "F_PC_SLEEP":
        return _calculate_state_change(resolved, "PC_BASE_W", "PC_TARGET_W", "PC_TARGET_COUNT", "PC_SAVABLE_HOURS", "OCCURRENCE_DAYS")
    if formula_id == "F_MONITOR_SLEEP":
        return _calculate_state_change(resolved, "MONITOR_ON_W", "MONITOR_TARGET_W", "MONITOR_TARGET_COUNT", "MONITOR_SAVABLE_HOURS", "OCCURRENCE_DAYS")
    if formula_id == "F_STANDBY_CUTOFF":
        if resolved.get("SHUTDOWN_ALLOWED", {}).get("value") is not True:
            raise CalculationError("SHUTDOWN_ALLOWED=true가 확인되지 않아 대기전력 차단 계산을 수행하지 않습니다.")
        return _calculate_state_change(resolved, "STANDBY_W", "CUTOFF_W", "STANDBY_COUNT", "CUTOFF_HOURS", "OCCURRENCE_DAYS")
    if formula_id == "F_EQUIPMENT_TIME":
        return _calculate_state_change(resolved, "EQUIPMENT_BASE_W", "EQUIPMENT_TARGET_W", "EQUIPMENT_COUNT", "EQUIPMENT_CHANGE_HOURS", "OCCURRENCE_DAYS")
    if formula_id == "F_LIGHT_OFF":
        w = _numeric_interval(resolved["LIGHT_W"], "LIGHT_W")
        count = _numeric_interval(resolved["LIGHT_TARGET_COUNT"], "LIGHT_TARGET_COUNT")
        hours = _numeric_interval(resolved["LIGHT_OFF_HOURS"], "LIGHT_OFF_HOURS")
        days = _numeric_interval(resolved["OPERATING_DAYS"], "OPERATING_DAYS")
        lo, hi = _multiply_nonnegative_intervals([w, count, hours, days])
        return (lo / 1000 if lo is not None else None, hi / 1000 if hi is not None else None, [])
    if formula_id == "F_POWER_INTERVAL":
        base = (resolved["BASE_W_MIN"].get("value_min"), resolved["BASE_W_MAX"].get("value_max") or resolved["BASE_W_MAX"].get("value_min"))
        target = (resolved["TARGET_W_MIN"].get("value_min"), resolved["TARGET_W_MAX"].get("value_max") or resolved["TARGET_W_MAX"].get("value_min"))
        delta = _difference_interval(base, target)
        hours = _numeric_interval(resolved["DEVICE_HOURS"], "DEVICE_HOURS")
        lo, hi = _multiply_nonnegative_intervals([delta, hours])
        return (lo / 1000 if lo is not None else None, hi / 1000 if hi is not None else None, [])
    raise CalculationError(f"현재 계산 엔진에 dispatch가 구현되지 않은 formula_id: {formula_id}")


def calculate_energy_saving(formula_id: str, resolved_inputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    lo, hi, warnings = _dispatch_energy_formula(formula_id, resolved_inputs)
    return {"energy_saving_kwh_min": lo, "energy_saving_kwh_max": hi, "warnings": warnings}


def _applicability_matches(row: Dict[str, Any], tariff_context: Dict[str, Any]) -> bool:
    app = row.get("applicability") or {}
    mapping = {
        "contract_type": "contract_type",
        "voltage": "voltage_class",
        "option": "tariff_option",
        "season": "season",
        "band": "band",
    }
    for app_key, ctx_key in mapping.items():
        expected = app.get(app_key)
        if expected is None:
            continue
        actual = tariff_context.get(ctx_key)
        if actual is None:
            return False
        if str(actual).upper() != str(expected).upper():
            return False
    app_region = app.get("region")
    if app_region:
        ctx_region = tariff_context.get("region")
        if ctx_region is None:
            return False
        normalized = "KR" if str(ctx_region).upper() == "MAINLAND" else str(ctx_region).upper()
        if normalized != str(app_region).upper():
            return False
    return True


def _tariff_missing_fields(tariff_context: Optional[Dict[str, Any]]) -> List[str]:
    if not tariff_context:
        return ["CONTRACT_TYPE", "VOLTAGE_CLASS", "TARIFF_OPTION", "SEASON", "REGION"]
    fields = []
    required = {
        "contract_type": "CONTRACT_TYPE",
        "voltage_class": "VOLTAGE_CLASS",
        "tariff_option": "TARIFF_OPTION",
        "season": "SEASON",
        "region": "REGION",
    }
    for key, label in required.items():
        if tariff_context.get(key) in (None, "", "UNKNOWN"):
            fields.append(label)
    # TOU plans need a band unless the applicable tariff is an all-day tariff.
    return fields


def calculate_cost_saving(
    energy_saving_kwh_min: Optional[float],
    energy_saving_kwh_max: Optional[float],
    tariff_context: Optional[Dict[str, Any]],
    reference_path: Path = DEFAULT_REFERENCE_PATH,
) -> Dict[str, Any]:
    if energy_saving_kwh_min is None and energy_saving_kwh_max is None:
        return {"cost_saving_krw_min": None, "cost_saving_krw_max": None, "reference_id": None, "missing_inputs": []}

    missing = _tariff_missing_fields(tariff_context)
    if missing:
        return {"cost_saving_krw_min": None, "cost_saving_krw_max": None, "reference_id": None, "missing_inputs": missing}

    tariff_context = dict(tariff_context or {})
    candidates = []
    for row in load_reference_db(reference_path):
        app = row.get("applicability") or {}
        if row.get("parameter") != "energy_rate":
            continue
        if app.get("calculation_eligible") is not True:
            continue
        if row.get("value_min") is None or row.get("value_max") is None or row.get("value_min") != row.get("value_max"):
            continue
        if _applicability_matches(row, tariff_context):
            candidates.append(row)

    # If no exact all-day match, a TOU tariff may require explicit band.
    if not candidates and not tariff_context.get("band"):
        tariff_context["band"] = "all"
        for row in load_reference_db(reference_path):
            app = row.get("applicability") or {}
            if row.get("parameter") != "energy_rate" or app.get("calculation_eligible") is not True:
                continue
            if row.get("value_min") is None or row.get("value_min") != row.get("value_max"):
                continue
            if _applicability_matches(row, tariff_context):
                candidates.append(row)

    if len(candidates) != 1:
        missing = ["TIME_PERIOD/BAND"] if any((r.get("applicability") or {}).get("band") not in (None, "all") for r in load_reference_db(reference_path) if r.get("parameter") == "energy_rate") else []
        return {"cost_saving_krw_min": None, "cost_saving_krw_max": None, "reference_id": None, "missing_inputs": missing or ["UNAMBIGUOUS_TARIFF_RATE"]}

    rate_row = candidates[0]
    rate = float(rate_row["value_min"])
    return {
        "cost_saving_krw_min": energy_saving_kwh_min * rate if energy_saving_kwh_min is not None else None,
        "cost_saving_krw_max": energy_saving_kwh_max * rate if energy_saving_kwh_max is not None else None,
        "reference_id": rate_row["reference_id"],
        "missing_inputs": [],
    }


def _confidence_and_status(resolved: Dict[str, Dict[str, Any]], required_inputs: List[str]) -> Tuple[str, str]:
    used = [resolved[k] for k in required_inputs if k in resolved]
    if any(v.get("evidence_class") == "ASSUMPTION" for v in used):
        return "LOW", "ESTIMATED"
    if any(v.get("evidence_class") in {"OFFICIAL", "MANUFACTURER"} for v in used):
        return "MEDIUM", "ESTIMATED"
    return "HIGH", "CALCULATED"


def _serialize_used_inputs(resolved: Dict[str, Dict[str, Any]], required_inputs: List[str]) -> Dict[str, Any]:
    out = {}
    for key in required_inputs:
        if key not in resolved:
            continue
        rec = resolved[key]
        if "value" in rec:
            value = rec.get("value")
        elif rec.get("value_min") == rec.get("value_max") and rec.get("value_min") is not None:
            value = rec.get("value_min")
        else:
            value = {"min": rec.get("value_min"), "max": rec.get("value_max")}
        out[key] = {
            "value": value,
            "unit": rec.get("unit"),
            "source": rec.get("source"),
            "evidence_class": rec.get("evidence_class"),
            "source_ref": rec.get("source_ref"),
        }
    return out


def calculate_solution_saving(
    solution: Dict[str, Any],
    answers: Dict[str, Any],
    user_measurements: Optional[Dict[str, Any]] = None,
    tariff_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    solution_id = solution.get("solution_id")
    waste_code = solution.get("waste_code")
    formula_id = solution.get("formula_id") or ""
    base_result: Dict[str, Any] = {
        "solution_id": solution_id,
        "waste_code": waste_code,
        "formula_id": formula_id or None,
        "calculation_status": None,
        "energy_saving_kwh_min": None,
        "energy_saving_kwh_max": None,
        "cost_saving_krw_min": None,
        "cost_saving_krw_max": None,
        "confidence": None,
        "used_inputs": {},
        "used_references": [],
        "assumptions": [],
        "missing_inputs": [],
        "warnings": [],
        "overlap_group": OVERLAP_GROUP.get(solution_id),
    }

    if not bool(solution.get("calculation_available")):
        base_result["calculation_status"] = "NOT_CALCULABLE"
        base_result["warnings"].append("이 솔루션은 현재 MVP에서 정량 절감량을 계산하지 않고 점검/측정 대상으로만 표시합니다.")
        return base_result

    formulas = {row["formula_id"]: row for row in load_formula_db(DEFAULT_FORMULA_PATH)}
    if not formula_id or formula_id not in formulas:
        base_result["calculation_status"] = "FORMULA_NOT_FOUND"
        base_result["missing_inputs"] = [formula_id or "formula_id"]
        return base_result

    context = dict(SOLUTION_CONTEXT.get(solution_id, {}))
    user_measurements = user_measurements or {}
    for key in ("PC_MODEL", "MONITOR_MODEL", "AC_MODEL"):
        if key in user_measurements:
            raw = user_measurements[key]
            context[key] = raw.get("value") if isinstance(raw, dict) and "value" in raw else raw

    resolved_pack = resolve_formula_inputs(formula_id, answers, user_measurements, context)
    formula = resolved_pack["formula"]
    resolved = resolved_pack["resolved"]
    base_result["used_references"] = list(resolved_pack["used_references"])
    base_result["assumptions"] = list(dict.fromkeys(resolved_pack["assumptions"]))
    base_result["missing_inputs"] = list(resolved_pack["missing_inputs"])
    base_result["used_inputs"] = _serialize_used_inputs(resolved, formula["required_inputs"]) if formula else {}

    if solution.get("requires_measurement"):
        # Measurement-required solutions must not be satisfied by a generic regulatory/average value.
        power_keys = [k for k in formula["required_inputs"] if k.endswith("_W")]
        not_measured = [k for k in power_keys if k in resolved and resolved[k].get("evidence_class") != "MEASURED"]
        if not_measured:
            base_result["missing_inputs"].extend([f"MEASURED:{k}" for k in not_measured])

    base_result["missing_inputs"] = sorted(set(base_result["missing_inputs"]))
    if base_result["missing_inputs"]:
        base_result["calculation_status"] = "NEEDS_INPUT"
        return base_result

    try:
        energy = calculate_energy_saving(formula_id, resolved)
    except CalculationError as exc:
        base_result["calculation_status"] = "NEEDS_INPUT"
        base_result["warnings"].append(str(exc))
        return base_result

    base_result.update({k: energy[k] for k in ("energy_saving_kwh_min", "energy_saving_kwh_max")})
    base_result["warnings"].extend(energy.get("warnings", []))

    confidence, status = _confidence_and_status(resolved, formula["required_inputs"])
    base_result["confidence"] = confidence
    base_result["calculation_status"] = status

    # Sanity check against known monthly usage. This flags rather than silently capping the result.
    survey_inputs = resolve_survey_inputs(answers)
    monthly_usage = survey_inputs.get("MONTHLY_USAGE_KWH")
    if monthly_usage and monthly_usage.get("value_min") is not None:
        baseline = float(monthly_usage["value_min"])
        if base_result["energy_saving_kwh_min"] is not None and base_result["energy_saving_kwh_min"] > baseline:
            base_result["warnings"].append("계산된 예상 절감량의 최소값이 현재 월 전기사용량을 초과합니다. 입력 기간/경계를 재검토하세요.")
        elif base_result["energy_saving_kwh_max"] is not None and base_result["energy_saving_kwh_max"] > baseline:
            base_result["warnings"].append("계산된 예상 절감량의 최대값이 현재 월 전기사용량을 초과합니다. 입력 기간/경계를 재검토하세요.")

    cost = calculate_cost_saving(
        base_result["energy_saving_kwh_min"], base_result["energy_saving_kwh_max"], tariff_context
    )
    base_result["cost_saving_krw_min"] = cost["cost_saving_krw_min"]
    base_result["cost_saving_krw_max"] = cost["cost_saving_krw_max"]
    if cost.get("reference_id"):
        base_result["used_references"] = sorted(set(base_result["used_references"] + [cost["reference_id"]]))
    if cost.get("missing_inputs"):
        base_result["warnings"].append(
            "전력량 절감은 계산했지만 요금 조건이 부족하여 예상 전력량요금 절감액은 계산하지 않았습니다: "
            + ", ".join(cost["missing_inputs"])
        )

    return base_result


def calculate_all_solutions(
    solutions: List[Dict[str, Any]],
    answers: Dict[str, Any],
    user_measurements: Optional[Dict[str, Any]] = None,
    tariff_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Calculate each solution independently. Never sums overlapping solution savings."""
    return [
        calculate_solution_saving(solution, answers, user_measurements, tariff_context)
        for solution in solutions
    ]
