import csv
from pathlib import Path
from typing import List, Dict, Any, Union

def _parse_bool(val: str) -> bool:
    return val.strip().upper() == "TRUE"

def load_solution_catalog(path: Union[str, Path] = "data/03_solution/solution_catalog.csv") -> List[Dict[str, Any]]:
    catalog = []
    file_path = Path(path)
    if not file_path.is_absolute() and not file_path.exists():
        file_path = Path(__file__).resolve().parents[1] / file_path
    if not file_path.exists():
        raise FileNotFoundError(f"Solution catalog not found: {path}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            catalog.append({
                "solution_id": row["solution_id"],
                "waste_code": row["waste_code"],
                "solution_name": row["solution_name"],
                "solution_type": row["solution_type"],
                "calculation_available": _parse_bool(row["calculation_available"]),
                "formula_id": row["formula_id"],
                "requires_measurement": _parse_bool(row["requires_measurement"]),
                "rag_query": row["rag_query"]
            })
    return catalog

def get_solutions_for_waste_code(waste_code: str, catalog: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [sol for sol in catalog if sol["waste_code"] == waste_code]

def recommend_solutions(risk_results: List[Dict[str, Any]], catalog_path: str = "data/03_solution/solution_catalog.csv") -> List[Dict[str, Any]]:
    catalog = load_solution_catalog(catalog_path)
    recommended = []
    
    for risk in risk_results:
        w_code = risk["waste_code"]
        r_score = risk.get("risk_score", 0)
        r_level = risk.get("risk_level", "LOW")
        needs_conf = risk.get("needs_confirmation", False)
        
        sols = get_solutions_for_waste_code(w_code, catalog)
        
        # Rule 1 & 3: 존재하지 않는 waste_code에 대해 임의 솔루션을 생성하지 않고 건너뜀
        if not sols:
            continue
            
        for sol in sols:
            output = {
                "solution_id": sol["solution_id"],
                "waste_code": sol["waste_code"],
                "solution_name": sol["solution_name"],
                "solution_type": sol["solution_type"],
                "risk_score": r_score,
                "risk_level": r_level,
                "calculation_available": sol["calculation_available"],
                "formula_id": sol["formula_id"],
                "requires_measurement": sol["requires_measurement"],
                "rag_query": sol["rag_query"],
                "needs_confirmation": needs_conf
            }
            
            # Rule 4: needs_confirmation=true 이고 ACTION인 경우 바로 실행 권고 처리 방지
            if needs_conf and sol["solution_type"] == "ACTION":
                output["confirmation_required"] = True
            elif needs_conf:
                # CHECK나 MEASURE 타입이어도 상태 확인 안내 목적으로 플래그 유지
                output["confirmation_required"] = True
                
            recommended.append(output)
            
    return recommended