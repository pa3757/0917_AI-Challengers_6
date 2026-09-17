from pathlib import Path
import json
import pytest
from src.survey_loader import load_survey_questions

SURVEY_PATH = Path(__file__).resolve().parents[1] / "data/01_survey/survey_questions.json"


def test_utf8_loading():
    """8. JSON을 UTF-8로 정상 로딩할 수 있는가"""
    assert SURVEY_PATH.exists(), "JSON 파일이 존재하지 않습니다."
    with open(SURVEY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)


def test_question_count():
    """1. Q01~Q17 총 17개의 질문이 존재하는가"""
    questions = load_survey_questions(SURVEY_PATH)
    assert len(questions) == 17, f"질문 개수가 17개가 아닙니다: {len(questions)}개"


def test_unique_question_ids():
    """2. question_id가 중복되지 않는가"""
    questions = load_survey_questions(SURVEY_PATH)
    q_ids = [q["question_id"] for q in questions]
    assert len(q_ids) == len(set(q_ids)), "question_id에 중복이 존재합니다."


def test_question_sequence():
    """3. Q01~Q17 순서가 유지되는가"""
    questions = load_survey_questions(SURVEY_PATH)
    expected_ids = [f"Q{i:02d}" for i in range(1, 18)]
    actual_ids = [q["question_id"] for q in questions]
    assert actual_ids == expected_ids, f"질문 순서가 올바르지 않습니다: {actual_ids}"


def test_single_select_has_options():
    """4. 모든 single_select 질문에 options가 존재하는가"""
    questions = load_survey_questions(SURVEY_PATH)
    for q in questions:
        if q["type"] == "single_select":
            assert "options" in q and isinstance(q["options"], list) and len(q["options"]) > 0, (
                f"질문 {q['question_id']}의 options가 올바르지 않습니다."
            )


def test_unique_option_codes_within_question():
    """5. 각 질문 내부 option code가 중복되지 않는가"""
    questions = load_survey_questions(SURVEY_PATH)
    for q in questions:
        if q["type"] == "single_select":
            codes = [opt["code"] for opt in q["options"]]
            assert len(codes) == len(set(codes)), f"질문 {q['question_id']} 내 중복된 option code가 있습니다."


def test_number_type_validations():
    """6. number 타입 질문의 validation min/max가 정상인가"""
    questions = load_survey_questions(SURVEY_PATH)
    for q in questions:
        if q["type"] == "number":
            assert "validation" in q, f"질문 {q['question_id']}에 validation 필드가 없습니다."
            val = q["validation"]
            if "min" in val and "max" in val:
                assert val["min"] <= val["max"], f"질문 {q['question_id']}의 min이 max보다 큽니다."


def test_prohibited_fields_absent():
    """7. survey_questions.json에 비즈니스 규칙 필드가 실수로 포함되어 있지 않은가"""
    prohibited_fields = [
        "risk_score",
        "risk_points",
        "waste_code",
        "risk_level",
        "solution_id",
        "formula_id",
        "reduction_formula",
        "electricity_cost_formula",
        "rag_context"
    ]
    questions = load_survey_questions(SURVEY_PATH)
    for q in questions:
        for field in prohibited_fields:
            assert field not in q, f"질문 {q['question_id']}에 금지 필드 '{field}'가 포함되어 있습니다."
            if "options" in q:
                for opt in q["options"]:
                    assert field not in opt, f"질문 {q['question_id']} 옵션 {opt.get('code')}에 금지 필드 '{field}'가 포함되어 있습니다."
