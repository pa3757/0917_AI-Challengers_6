import json
from pathlib import Path
from typing import Any, Dict, List, Union


def load_survey_questions(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """설문 정의 JSON 파일을 검증하고 로드합니다."""
    file_path = Path(path)
    if not file_path.exists():
        raise ValueError(f"파일을 찾을 수 없습니다: {path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError(f"JSON 파싱 실패 ({path}): {e}")

    if not isinstance(data, list):
        raise ValueError("최상위 구조는 JSON Array(List)여야 합니다.")

    required_fields = ["question_id", "section", "category", "question", "type", "required", "purpose"]
    seen_ids = set()

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"인덱스 {idx}: 각 질문은 JSON Object(Dict) 형태여야 합니다.")

        # 필수 필드 검사
        for field in required_fields:
            if field not in item:
                raise ValueError(f"질문 {item.get('question_id', f'Index {idx}')}: 필수 필드 '{field}'가 누락되었습니다.")

        qid = item["question_id"]

        # 중복 ID 검사
        if qid in seen_ids:
            raise ValueError(f"중복된 question_id가 발견되었습니다: '{qid}'")
        seen_ids.add(qid)

        # single_select 검증
        if item["type"] == "single_select":
            if "options" not in item or not isinstance(item["options"], list) or len(item["options"]) == 0:
                raise ValueError(f"질문 '{qid}': single_select 타입은 1개 이상의 options 리스트를 포함해야 합니다.")

            seen_codes = set()
            for opt_idx, opt in enumerate(item["options"]):
                if not isinstance(opt, dict) or "code" not in opt or "label" not in opt:
                    raise ValueError(f"질문 '{qid}' 옵션 [{opt_idx}]: code와 label 필드가 필수입니다.")

                code = opt["code"]
                if code in seen_codes:
                    raise ValueError(f"질문 '{qid}': 옵션 내 중복된 option code가 발견되었습니다: '{code}'")
                seen_codes.add(code)

    return data