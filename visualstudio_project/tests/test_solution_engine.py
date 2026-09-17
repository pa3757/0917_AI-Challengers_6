import pytest
from src.solution_engine import recommend_solutions, load_solution_catalog

def test_case_1_pc_idle_window_leak():
    """CASE 1: 정상적인 솔루션 매핑 검증"""
    results = [{"waste_code": "PC_IDLE_WINDOW_LEAK", "risk_score": 7, "risk_level": "HIGH", "needs_confirmation": False}]
    sols = recommend_solutions(results)
    assert len(sols) == 1
    assert sols[0]["solution_id"] == "SOL_PC_003"
    assert sols[0]["solution_type"] == "ACTION"
    assert sols[0]["risk_score"] == 7

def test_case_2_hidden_baseload_risk():
    """CASE 2: 측정 타입 솔루션 매핑 검증"""
    results = [{"waste_code": "HIDDEN_BASELOAD_RISK", "risk_score": 4, "risk_level": "MEDIUM", "needs_confirmation": False}]
    sols = recommend_solutions(results)
    assert len(sols) == 1
    assert sols[0]["solution_id"] == "SOL_OPS_002"
    assert sols[0]["solution_type"] == "MEASURE"

def test_case_3_refrig_defrost_control_needs_conf():
    """CASE 3: 제상 설정은 임의 변경 방지 및 확인 권고(confirmation_required) 발동 검증"""
    results = [{"waste_code": "REFRIG_DEFROST_CONTROL", "risk_score": 0, "risk_level": "LOW", "needs_confirmation": True}]
    sols = recommend_solutions(results)
    assert len(sols) == 1
    assert sols[0]["solution_id"] == "SOL_REF_002"
    assert sols[0]["solution_type"] == "CHECK"
    assert sols[0]["confirmation_required"] is True

def test_case_4_pc_off_standby_leak():
    """CASE 4: Calculation 및 Measurement 플래그 정상 유지 확인"""
    results = [{"waste_code": "PC_OFF_STANDBY_LEAK", "risk_score": 3, "risk_level": "MEDIUM", "needs_confirmation": False}]
    sols = recommend_solutions(results)
    assert len(sols) == 1
    assert sols[0]["calculation_available"] is True
    assert sols[0]["requires_measurement"] is True

def test_case_5_hvac_outdoor_heat():
    """CASE 5: 실외기 등 계산 불가 솔루션 플래그 검증"""
    results = [{"waste_code": "HVAC_OUTDOOR_HEAT_RECIRCULATION", "risk_score": 5, "risk_level": "MEDIUM", "needs_confirmation": False}]
    sols = recommend_solutions(results)
    assert len(sols) == 1
    assert sols[0]["calculation_available"] is False

def test_case_6_invalid_waste_code():
    """CASE 6: 존재하지 않는 waste_code에 대해 임의 솔루션 생성 방지"""
    results = [{"waste_code": "INVALID_CODE_999", "risk_score": 5, "risk_level": "MEDIUM", "needs_confirmation": False}]
    sols = recommend_solutions(results)
    assert len(sols) == 0

def test_case_7_empty_results():
    """CASE 7: 빈 리스트 방어 로직"""
    assert len(recommend_solutions([])) == 0