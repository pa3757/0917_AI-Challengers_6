"""Calculation Engine input resolution utilities.

This module deliberately keeps numeric calculation inputs separate from RAG.
It never substitutes regulatory limits/certification thresholds for actual power.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CALC_DIR = PROJECT_ROOT / "data" / "05_calculation"
DEFAULT_MAPPING_PATH = CALC_DIR / "survey_numeric_mapping.csv"
DEFAULT_REFERENCE_PATH = CALC_DIR / "PC방_Calculation_Reference_DB.csv"
DEFAULT_FORMULA_PATH = CALC_DIR / "PC방_Calculation_Formulas.csv"
DEFAULT_USER_INPUT_PATH = CALC_DIR / "PC방_Calculation_User_Inputs.csv"

# These reference types are standards/limits, not observed or model-specific actual values.
EXCLUDED_ACTUAL_REFERENCE_TYPES = {
    "regulatory_limit",
    "regulatory_allowance",
    "certification_threshold",
    "maximum_limit",
    "minimum_standard",
}


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_or_default(value: Any, default: Any) -> Any:
    if value is None or str(value).strip() == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _read_csv(path: Union[str, Path]) -> List[Dict[str, str]]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {file_path}")
    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_numeric_mapping(path: Union[str, Path] = DEFAULT_MAPPING_PATH) -> List[Dict[str, Any]]:
    rows = []
    for row in _read_csv(path):
        rows.append(
            {
                **row,
                "value_min": _float_or_none(row.get("value_min")),
                "value_max": _float_or_none(row.get("value_max")),
            }
        )
    return rows


def load_reference_db(path: Union[str, Path] = DEFAULT_REFERENCE_PATH) -> List[Dict[str, Any]]:
    rows = []
    for row in _read_csv(path):
        rows.append(
            {
                **row,
                "value_min": _float_or_none(row.get("value_min")),
                "value_max": _float_or_none(row.get("value_max")),
                "applicability": _json_or_default(row.get("applicability"), {}),
            }
        )
    return rows


def load_formula_db(path: Union[str, Path] = DEFAULT_FORMULA_PATH) -> List[Dict[str, Any]]:
    rows = []
    for row in _read_csv(path):
        rows.append(
            {
                **row,
                "required_inputs": _json_or_default(row.get("required_inputs"), []),
                "optional_inputs": _json_or_default(row.get("optional_inputs"), []),
                "reference_parameters": _json_or_default(row.get("reference_parameters"), []),
                "limitations": _json_or_default(row.get("limitations"), {}),
            }
        )
    return rows


def load_user_input_definitions(path: Union[str, Path] = DEFAULT_USER_INPUT_PATH) -> List[Dict[str, Any]]:
    rows = []
    for row in _read_csv(path):
        rows.append(
            {
                **row,
                "validation_rule": _json_or_default(row.get("validation_rule"), {}),
                "used_for": _json_or_default(row.get("used_for"), []),
            }
        )
    return rows


def _value_record(
    value_min: Optional[float],
    value_max: Optional[float],
    unit: str,
    source: str,
    evidence_class: str,
    source_ref: Optional[str] = None,
    state: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "value_min": value_min,
        "value_max": value_max,
        "unit": unit,
        "source": source,
        "evidence_class": evidence_class,
        "source_ref": source_ref,
        "state": state,
        "notes": notes,
    }


def _normalize_user_value(input_id: str, raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        # Rich input form: {value: x, evidence_class: ..., source_ref: ...}
        if "value" in raw:
            value = _float_or_none(raw.get("value"))
            if value is None and not isinstance(raw.get("value"), bool):
                # non-numeric values such as strings/JSON objects are kept verbatim
                return {
                    "value": raw.get("value"),
                    "value_min": None,
                    "value_max": None,
                    "unit": raw.get("unit", ""),
                    "source": raw.get("source", "USER_INPUT"),
                    "evidence_class": raw.get("evidence_class", "MEASURED"),
                    "source_ref": raw.get("source_ref", input_id),
                    "state": raw.get("state"),
                    "notes": raw.get("notes"),
                }
            return _value_record(
                value,
                value,
                raw.get("unit", ""),
                raw.get("source", "USER_INPUT"),
                raw.get("evidence_class", "MEASURED"),
                raw.get("source_ref", input_id),
                raw.get("state"),
                raw.get("notes"),
            )
        if "value_min" in raw or "value_max" in raw:
            return _value_record(
                _float_or_none(raw.get("value_min")),
                _float_or_none(raw.get("value_max")),
                raw.get("unit", ""),
                raw.get("source", "USER_INPUT"),
                raw.get("evidence_class", "ASSUMPTION"),
                raw.get("source_ref", input_id),
                raw.get("state"),
                raw.get("notes"),
            )
        # JSON object input required by some formulas.
        return {
            "value": raw,
            "value_min": None,
            "value_max": None,
            "unit": "",
            "source": "USER_INPUT",
            "evidence_class": "MEASURED",
            "source_ref": input_id,
            "state": None,
            "notes": None,
        }

    if isinstance(raw, bool):
        return {
            "value": raw,
            "value_min": None,
            "value_max": None,
            "unit": "",
            "source": "USER_INPUT",
            "evidence_class": "MEASURED",
            "source_ref": input_id,
            "state": None,
            "notes": None,
        }

    number = _float_or_none(raw)
    if number is not None:
        return _value_record(number, number, "", "USER_INPUT", "MEASURED", input_id)

    return {
        "value": raw,
        "value_min": None,
        "value_max": None,
        "unit": "",
        "source": "USER_INPUT",
        "evidence_class": "MEASURED",
        "source_ref": input_id,
        "state": None,
        "notes": None,
    }


def resolve_survey_inputs(
    answers: Dict[str, Any],
    mapping_path: Union[str, Path] = DEFAULT_MAPPING_PATH,
) -> Dict[str, Dict[str, Any]]:
    """Resolve only survey values that can be represented without inventing a point estimate."""
    resolved: Dict[str, Dict[str, Any]] = {}

    direct = {
        "Q01": ("PC_COUNT", "count"),
        "Q02": ("BUSINESS_HOURS", "h/day"),
        "Q04": ("MONTHLY_USAGE_KWH", "kWh"),
    }
    for qid, (parameter, unit) in direct.items():
        raw = answers.get(qid)
        if raw is None or raw == "UNKNOWN":
            continue
        value = _float_or_none(raw)
        if value is None:
            continue
        resolved[parameter] = _value_record(
            value, value, unit, "SURVEY", "MEASURED", qid, notes=f"{qid} 직접 숫자 응답"
        )

    mapping_index = {
        (row["question_id"], row["answer_code"]): row for row in load_numeric_mapping(mapping_path)
    }
    for qid, raw in answers.items():
        if not isinstance(raw, str):
            continue
        row = mapping_index.get((qid, raw))
        if not row:
            continue
        if row.get("mapping_type") in {"unknown", "non_numeric"}:
            continue
        resolved[row["parameter"]] = _value_record(
            row.get("value_min"),
            row.get("value_max"),
            row.get("unit", ""),
            "SURVEY_RANGE",
            "ASSUMPTION" if row.get("mapping_type") != "point" else "MEASURED",
            row.get("mapping_id"),
            notes=row.get("notes"),
        )

    return resolved


def _reference_model(row: Dict[str, Any]) -> Optional[str]:
    app = row.get("applicability") or {}
    model = app.get("model")
    return str(model) if model else None


def _is_reference_calculable(row: Dict[str, Any]) -> bool:
    app = row.get("applicability") or {}
    if app.get("calculation_eligible") is not True:
        return False
    if str(row.get("reference_type", "")).strip().lower() in EXCLUDED_ACTUAL_REFERENCE_TYPES:
        return False
    if row.get("value_min") is None and row.get("value_max") is None:
        return False
    return True


def _reference_candidates_for_parameter(parameter: str, context: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return (equipment, db_parameter, state, model)."""
    if parameter in {"PC_BASE_W", "PC_TARGET_W"}:
        state = context.get("PC_BASE_STATE" if parameter == "PC_BASE_W" else "PC_TARGET_STATE")
        return "desktop_computer", "power_consumption", state, context.get("PC_MODEL")
    if parameter in {"MONITOR_ON_W", "MONITOR_TARGET_W", "MONITOR_SLEEP_W", "MONITOR_OFF_W"}:
        if parameter == "MONITOR_ON_W":
            state = "on"
        elif parameter in {"MONITOR_TARGET_W", "MONITOR_SLEEP_W"}:
            state = context.get("MONITOR_TARGET_STATE", "sleep")
        else:
            state = "off"
        return "computer_monitor", "power_consumption", state, context.get("MONITOR_MODEL")
    if parameter == "AC_RATED_INPUT_W":
        return "air_conditioner", "rated_electric_input", "cooling", context.get("AC_MODEL")
    return None, None, None, None


def resolve_reference_value(
    parameter: str,
    user_measurements: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    reference_path: Union[str, Path] = DEFAULT_REFERENCE_PATH,
) -> Optional[Dict[str, Any]]:
    """Resolve an exact calculation value without using regulatory limits as actual consumption."""
    user_measurements = user_measurements or {}
    context = context or {}

    if parameter in user_measurements:
        return _normalize_user_value(parameter, user_measurements[parameter])

    equipment, db_parameter, state, model = _reference_candidates_for_parameter(parameter, context)
    if not equipment or not db_parameter or not state:
        return None

    candidates: List[Dict[str, Any]] = []
    for row in load_reference_db(reference_path):
        if row.get("equipment") != equipment:
            continue
        if row.get("parameter") != db_parameter or row.get("state") != state:
            continue
        if not _is_reference_calculable(row):
            continue
        ref_model = _reference_model(row)
        if ref_model:
            if not model or str(model).strip().lower() != ref_model.strip().lower():
                continue
        elif model:
            # A generic calculable reference may still be used only if the DB explicitly marks it calculable.
            pass
        candidates.append(row)

    if not candidates:
        return None

    # Prefer exact model point values, then other eligible point/range references.
    candidates.sort(
        key=lambda r: (
            0 if _reference_model(r) and model else 1,
            0 if r.get("value_min") is not None and r.get("value_min") == r.get("value_max") else 1,
            r.get("reference_id", ""),
        )
    )
    row = candidates[0]
    evidence = str(row.get("reference_type") or "OFFICIAL").upper()
    if evidence not in {"MEASURED", "OFFICIAL", "MANUFACTURER", "ASSUMPTION"}:
        evidence = "OFFICIAL"
    return _value_record(
        row.get("value_min"),
        row.get("value_max"),
        row.get("unit", ""),
        "REFERENCE_DB",
        evidence,
        row.get("reference_id"),
        state=row.get("state"),
        notes=row.get("calculation_note"),
    )


def _derive_target_count(
    pc_count: Dict[str, Any], empty_rate: Dict[str, Any], parameter: str
) -> Dict[str, Any]:
    count = pc_count.get("value_min")
    if count is None:
        return _value_record(None, None, "count", "DERIVED", "ASSUMPTION", notes="PC_COUNT 없음")
    rate_min = empty_rate.get("value_min")
    rate_max = empty_rate.get("value_max")
    value_min = math.ceil(count * rate_min) if rate_min is not None else None
    value_max = math.floor(count * rate_max) if rate_max is not None else None
    return _value_record(
        float(value_min) if value_min is not None else None,
        float(value_max) if value_max is not None else None,
        "count",
        "DERIVED_FROM_SURVEY_RANGE",
        "ASSUMPTION",
        source_ref=f"PC_COUNT+EMPTY_SEAT_RATE->{parameter}",
        notes="전체 PC 수와 빈 좌석률 설문 범위로 계산한 대상 수; 실제 대상 좌석 수 입력이 우선",
    )


def _choose_measured_alias(
    aliases: Iterable[str], user_measurements: Dict[str, Any]
) -> Optional[Tuple[str, Dict[str, Any]]]:
    for alias in aliases:
        if alias in user_measurements:
            record = _normalize_user_value(alias, user_measurements[alias])
            if record is not None:
                return alias, record
    return None


def resolve_formula_inputs(
    formula_id: str,
    answers: Dict[str, Any],
    user_measurements: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    formula_path: Union[str, Path] = DEFAULT_FORMULA_PATH,
    reference_path: Union[str, Path] = DEFAULT_REFERENCE_PATH,
    mapping_path: Union[str, Path] = DEFAULT_MAPPING_PATH,
) -> Dict[str, Any]:
    """Resolve required formula inputs, preserving ranges and provenance."""
    user_measurements = user_measurements or {}
    context = dict(context or {})
    formula_rows = {row["formula_id"]: row for row in load_formula_db(formula_path)}
    formula = formula_rows.get(formula_id)
    if formula is None:
        return {"formula": None, "resolved": {}, "missing_inputs": [], "used_references": [], "assumptions": []}

    survey = resolve_survey_inputs(answers, mapping_path)
    resolved: Dict[str, Dict[str, Any]] = dict(survey)

    # User inputs always override survey-derived values when the same input_id is explicitly supplied.
    for input_id, raw in user_measurements.items():
        normalized = _normalize_user_value(input_id, raw)
        if normalized is not None:
            resolved[input_id] = normalized

    # Common context fields may be supplied either in context or user_measurements.
    for key in ("PC_MODEL", "MONITOR_MODEL", "AC_MODEL"):
        if key in user_measurements and key not in context:
            raw = user_measurements[key]
            context[key] = raw.get("value") if isinstance(raw, dict) and "value" in raw else raw

    # Derive only counts that have a direct, transparent survey basis.
    if "PC_COUNT" in resolved and "EMPTY_SEAT_RATE" in resolved:
        if "PC_TARGET_COUNT" not in resolved:
            resolved["PC_TARGET_COUNT"] = _derive_target_count(resolved["PC_COUNT"], resolved["EMPTY_SEAT_RATE"], "PC_TARGET_COUNT")
        if "MONITOR_TARGET_COUNT" not in resolved:
            resolved["MONITOR_TARGET_COUNT"] = _derive_target_count(resolved["PC_COUNT"], resolved["EMPTY_SEAT_RATE"], "MONITOR_TARGET_COUNT")

    # Power-state aliases. We do not convert regulatory limits to point values.
    if formula_id == "F_PC_SLEEP":
        if "PC_BASE_W" not in resolved:
            base_state = context.get("PC_BASE_STATE", "idle")
            alias_order = ["PC_MEASURED_IDLE_W", "PC_MEASURED_ACTIVE_W"] if base_state == "idle" else ["PC_MEASURED_ACTIVE_W", "PC_MEASURED_IDLE_W"]
            picked = _choose_measured_alias(alias_order, user_measurements)
            if picked:
                _, resolved["PC_BASE_W"] = picked
            else:
                ref = resolve_reference_value("PC_BASE_W", user_measurements, context, reference_path)
                if ref:
                    resolved["PC_BASE_W"] = ref
        if "PC_TARGET_W" not in resolved:
            target_state = context.get("PC_TARGET_STATE", "sleep")
            alias_order = ["PC_MEASURED_SLEEP_W", "PC_MEASURED_OFF_W"] if target_state == "sleep" else ["PC_MEASURED_OFF_W", "PC_MEASURED_SLEEP_W"]
            picked = _choose_measured_alias(alias_order, user_measurements)
            if picked:
                _, resolved["PC_TARGET_W"] = picked
            else:
                ref = resolve_reference_value("PC_TARGET_W", user_measurements, context, reference_path)
                if ref:
                    resolved["PC_TARGET_W"] = ref

    elif formula_id == "F_MONITOR_SLEEP":
        if "MONITOR_ON_W" not in resolved:
            ref = resolve_reference_value("MONITOR_ON_W", user_measurements, context, reference_path)
            if ref:
                resolved["MONITOR_ON_W"] = ref
        if "MONITOR_TARGET_W" not in resolved:
            picked = _choose_measured_alias(["MONITOR_SLEEP_W", "MONITOR_OFF_W"], user_measurements)
            if picked:
                _, resolved["MONITOR_TARGET_W"] = picked
            else:
                ref = resolve_reference_value("MONITOR_TARGET_W", user_measurements, context, reference_path)
                if ref:
                    resolved["MONITOR_TARGET_W"] = ref

    # Generic reference resolver for still-unresolved required parameters.
    for parameter in formula["required_inputs"]:
        if parameter in resolved:
            continue
        ref = resolve_reference_value(parameter, user_measurements, context, reference_path)
        if ref:
            resolved[parameter] = ref

    missing: List[str] = []
    for parameter in formula["required_inputs"]:
        value = resolved.get(parameter)
        if value is None:
            missing.append(parameter)
            continue
        # JSON/bool/string required inputs use the 'value' key; numeric values use bounds.
        if "value" in value:
            if value.get("value") is None:
                missing.append(parameter)
        elif value.get("value_min") is None and value.get("value_max") is None:
            missing.append(parameter)

    used_references = sorted(
        {
            str(v.get("source_ref"))
            for key, v in resolved.items()
            if key in formula["required_inputs"] and v.get("source") == "REFERENCE_DB" and v.get("source_ref")
        }
    )
    assumptions = []
    for key, value in resolved.items():
        if key not in formula["required_inputs"]:
            continue
        if value.get("evidence_class") == "ASSUMPTION":
            note = value.get("notes") or f"{key}에 추정/범위 입력 사용"
            assumptions.append(note)

    return {
        "formula": formula,
        "resolved": resolved,
        "missing_inputs": sorted(set(missing)),
        "used_references": used_references,
        "assumptions": assumptions,
        "context": context,
    }
