# Calculation Engine 상태

## 구현 완료

- `data/05_calculation/survey_numeric_mapping.csv`
- `src/calculation_input_resolver.py`
- `src/calculator.py`
- `tests/test_calculation_input_resolver.py`
- `tests/test_calculator.py`
- `tests/test_pipeline_integration.py`

## 기존 구조 정리

- `survey_rules.csv`를 `data/02_risk/`로 이동해 `rule_engine.py` 기본 경로와 일치시킴.
- ZIP 문자 인코딩으로 깨진 한글 CSV 파일명을 정상화함.
- `src/__init__.py`, `tests/conftest.py`를 추가해 pytest import 오류를 해결함.

## Solution → Formula 연결 수정

기존 `solution_catalog.csv`의 `FORM_*` ID는 실제 `PC방_Calculation_Formulas.csv`에 존재하지 않아 아래와 같이 실제 Formula ID로 연결함.

- SOL_PC_001 → F_PC_SLEEP
- SOL_PC_002 → F_MONITOR_SLEEP
- SOL_PC_003 → F_PC_SLEEP
- SOL_PC_004 → F_PC_SLEEP
- SOL_PC_005 → F_STANDBY_CUTOFF
- SOL_PC_006 → F_STANDBY_CUTOFF

## 현재 설문에서 계산 입력으로 확보되는 값

- Q01 → PC_COUNT
- Q02 → BUSINESS_HOURS
- Q03 → EMPTY_SEAT_RATE 범위
- Q04 → MONTHLY_USAGE_KWH
- Q06 → IDLE_TRANSITION_TIME 범위

`Q03=EMPTY_51_PLUS`, `Q06=OVER_30_MIN`처럼 상한이 없는 응답은 임의 상한을 생성하지 않음.

## 현재 PC 절감 kWh 계산에 추가로 필요한 대표 값

### F_PC_SLEEP
- PC_BASE_W: 실측 또는 정확한 모델의 허용 가능한 실제 소비전력
- PC_TARGET_W: 실측 또는 정확한 모델의 목표상태 실제 소비전력
- PC_SAVABLE_HOURS: 하루 실제 절감 가능한 순시간
- OCCURRENCE_DAYS: 해당 현상이 발생하는 분석기간 내 일수

`PC_TARGET_COUNT`는 Q01 × Q03 범위로 투명하게 파생할 수 있으나, 실제 대상 PC 수 입력이 있으면 그 값을 우선함.

### F_MONITOR_SLEEP
- MONITOR_ON_W
- MONITOR_TARGET_W
- MONITOR_SAVABLE_HOURS
- OCCURRENCE_DAYS

### F_STANDBY_CUTOFF
- STANDBY_W
- CUTOFF_W
- STANDBY_COUNT
- CUTOFF_HOURS
- OCCURRENCE_DAYS
- SHUTDOWN_ALLOWED=true

## Reference DB 안전 규칙

- `regulatory_limit`, `regulatory_allowance`는 실제 소비전력으로 사용하지 않음.
- PC 일반 활성/유휴/슬립/오프 대표 W가 없으면 임의값 생성 없이 `NEEDS_INPUT` 반환.
- 정확한 모델과 계산 가능한 점값이 있을 때만 모델별 Reference 사용.
- 요금 조건이 부족하면 kWh만 계산하고 원화 비용은 `null`로 유지.

## 테스트

`pytest -q`

결과: **36 passed**
