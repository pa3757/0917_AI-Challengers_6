import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Set, Union


# MVP 내부 위험등급 판정 기준 (공공기관 공식 위험등급 아님)
def get_risk_level(score: int) -> str:
    """
    내부 진단 기준:
    0~2: LOW
    3~5: MEDIUM
    6 이상: HIGH
    """
    if score >= 6:
        return "HIGH"
    elif score >= 3:
        return "MEDIUM"
    else:
        return "LOW"


def load_survey_rules(path: Union[str, Path] = "data/02_risk/survey_rules.csv") -> List[Dict[str, Any]]:
    rules = []
    file_path = Path(path)
    if not file_path.is_absolute() and not file_path.exists():
        file_path = Path(__file__).resolve().parents[1] / file_path
    if not file_path.exists():
        raise FileNotFoundError(f"규칙 파일을 찾을 수 없습니다: {path}")

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rules.append({
                "rule_id": row["rule_id"],
                "question_id": row["question_id"],
                "answer_code": row["answer_code"],
                "waste_code": row["waste_code"],
                "risk_points": int(row["risk_points"]),
                "reason": row["reason"],
                "unknown_flag": row["unknown_flag"].strip().lower() == "true"
            })
    return rules


def load_composite_rules(path: Union[str, Path] = "data/02_risk/composite_rules.json") -> List[Dict[str, Any]]:
    file_path = Path(path)
    if not file_path.is_absolute() and not file_path.exists():
        file_path = Path(__file__).resolve().parents[1] / file_path
    if not file_path.exists():
        raise FileNotFoundError(f"복합 규칙 파일을 찾을 수 없습니다: {path}")

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _check_condition(user_val: Any, cond: Dict[str, Any]) -> bool:
    op = cond.get("op")
    target_val = cond.get("value")

    if user_val is None:
        return False

    if op == ">=":
        return float(user_val) >= float(target_val)
    elif op == "<=":
        return float(user_val) <= float(target_val)
    elif op == "==":
        return user_val == target_val
    elif op == "in":
        return user_val in target_val
    return False


def evaluate_single_rules(answers: Dict[str, Any], rules: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    results = {}

    for rule in rules:
        qid = rule["question_id"]
        user_ans = answers.get(qid)

        if user_ans is None:
            continue

        if user_ans == rule["answer_code"]:
            w_code = rule["waste_code"]
            if w_code not in results:
                results[w_code] = {
                    "waste_code": w_code,
                    "risk_score": 0,
                    "triggered_questions": set(),
                    "triggered_rules": [],
                    "reasons": [],
                    "needs_confirmation": False,
                    "has_composite": False
                }

            results[w_code]["risk_score"] += rule["risk_points"]
            results[w_code]["triggered_questions"].add(qid)
            results[w_code]["triggered_rules"].append(rule["rule_id"])
            if rule["reason"]:
                results[w_code]["reasons"].append(rule["reason"])
            if rule["unknown_flag"]:
                results[w_code]["needs_confirmation"] = True

    return results


def evaluate_composite_rules(answers: Dict[str, Any], composite_rules: List[Dict[str, Any]], results: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    for cr in composite_rules:
        conditions = cr["conditions"]
        matched = True
        triggered_qids = set()

        for qid, cond in conditions.items():
            user_val = answers.get(qid)
            if not _check_condition(user_val, cond):
                matched = False
                break
            triggered_qids.add(qid)

        if matched:
            w_code = cr["waste_code"]
            if w_code not in results:
                results[w_code] = {
                    "waste_code": w_code,
                    "risk_score": 0,
                    "triggered_questions": set(),
                    "triggered_rules": [],
                    "reasons": [],
                    "needs_confirmation": False,
                    "has_composite": False
                }

            results[w_code]["risk_score"] += cr["bonus_points"]
            results[w_code]["triggered_questions"].update(triggered_qids)
            results[w_code]["triggered_rules"].append(cr["rule_id"])
            results[w_code]["reasons"].append(cr["reason"])
            results[w_code]["has_composite"] = True

    return results


def evaluate_risks(
    answers: Dict[str, Any],
    rules_path: Union[str, Path] = "data/02_risk/survey_rules.csv",
    composite_path: Union[str, Path] = "data/02_risk/composite_rules.json"
) -> List[Dict[str, Any]]:
    single_rules = load_survey_rules(rules_path)
    comp_rules = load_composite_rules(composite_path)

    # 1. 단일 룰 검사
    results = evaluate_single_rules(answers, single_rules)

    # 2. 복합 룰 검사
    results = evaluate_composite_rules(answers, comp_rules, results)

    output = []
    for w_code, item in results.items():
        # 결과 필터링: risk_score > 0 또는 needs_confirmation == True 인 경우만
        if item["risk_score"] > 0 or item["needs_confirmation"]:
            output.append({
                "waste_code": w_code,
                "risk_score": item["risk_score"],
                "risk_level": get_risk_level(item["risk_score"]),
                "triggered_questions": sorted(list(item["triggered_questions"])),
                "triggered_rules": item["triggered_rules"],
                "reasons": item["reasons"],
                "needs_confirmation": item["needs_confirmation"],
                "has_composite": item["has_composite"]
            })

    # 정렬: risk_score 내림차순 -> 동점 시 composite_rule 유무 우대 -> waste_code 알파벳순
    output.sort(key=lambda x: (-x["risk_score"], -int(x["has_composite"]), x["waste_code"]))

    # 내부 플래그 삭제 후 최종 반환
    for item in output:
        del item["has_composite"]

    return output