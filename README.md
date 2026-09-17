# Energy Coach · FastAPI

`energy-coach.html`의 화면과 기존 Python 진단 엔진을 한 FastAPI 서버에서 제공합니다.

## 실행 (Windows PowerShell)

프로젝트 루트에서 실행합니다. 현재 작업 환경에는 `.venv`와 실행 패키지가 설치되어 있습니다.

```powershell
# 새 환경에서 최초 1회
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 서버 시작
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- 화면: http://127.0.0.1:8000
- API 문서: http://127.0.0.1:8000/docs
- 종료: 실행 터미널에서 Ctrl+C
- PowerShell 스크립트 실행이 허용된 환경에서는 `./run.ps1`도 사용할 수 있습니다.
- HTML 파일을 직접 더블클릭하지 말고 서버 주소로 접속하세요.

Node.js는 **화면 테스트에만** 사용하며 서비스 실행에는 필요하지 않습니다. 별도 Streamlit/프론트엔드 서버는 없습니다.

## 연결된 기능

1. 기존 JSON의 전체 17개 설문 문항 및 서버 입력 검증
2. 단일·복합 규칙 위험 진단 → 솔루션 매칭 → 근거 연결 → 절감량 계산 → 우선순위 Top 3
3. 실제 진단 결과, 실천 미션, 개별 예상 효과, 출처 및 추가 입력 안내
4. 측정값 입력 및 선택적 계약·계절·시간대 요금 조건
5. 미션 완료 기록, 업장명 저장, 새로고침 후 응답·결과 복원

원본 HTML의 색상, 글꼴, 휴대폰 프레임, 단계 이동, 탭, 카드, 버튼 스타일을 유지하고 카드 템플릿에 결과를 채웁니다. 기존 엔진에는 주방 전용 문항이 없어 해당 탭을 **운영 관리**로 맞추고 기본 정보 탭을 추가했습니다. 의미가 다른 예시 문항을 실제 문항에 임의 매핑하지 않습니다.

## 계산 및 근거 검색

- 기본 계산은 기존 `mvp_calculation_engine.py`의 참고 시나리오입니다. 입력 부족 시 내부 가정값을 사용하고 **130원/kWh**를 적용합니다. 실제 요금이나 확정 절감액이 아닙니다.
- 설문의 **MVP 참고 추정 사용**을 끄면 기존 정량 계산 엔진만 사용합니다. 측정값이 부족하면 숫자를 만들지 않고 추가 입력을 안내합니다. 요금 조건을 선택한 경우 기존 DB 요율로 전력량요금 절감을 계산합니다. 기본요금·세금·기타 청구항목은 포함하지 않습니다.
- 요금 조건 목록은 제공된 DB의 저장값이며 실시간 갱신하지 않습니다.
- 겹치는 개선 효과를 과대 합산하지 않도록 추천별 개별 수치를 표시합니다. 상단 효과 카드는 1순위 추천 기준입니다.
- 기본 근거 검색은 제공된 CSV에서 `waste_code`를 정확히 매칭합니다. 벡터 의미 검색이나 LLM 생성으로 표시하지 않습니다.
- 원본 `llm_service.py`, `survey_service.py`는 빈 파일입니다. 별도 LLM 생성 기능은 구현되어 있지 않았으며 현재는 기존 진단·계산·근거 데이터를 출력합니다.

기존 Chroma 의미 검색을 사용하려면 선택적으로 다음을 실행하세요. 임베딩 모델 최초 다운로드가 필요합니다.

```powershell
.venv\Scripts\python.exe -m pip install -r visualstudio_project/requirements.txt
.venv\Scripts\python.exe visualstudio_project/scripts/build_rag_index.py
$env:ENERGY_RAG_MODE = 'chroma'
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

인덱스가 없거나 검색 준비에 실패하면 503 오류를 표시하고 이전 결과를 보존합니다. 기본 `catalog` 모드에는 외부 API 키, Chroma, 임베딩 다운로드가 필요하지 않습니다.

## 상태 저장과 범위

- SQLite: `runtime/energy-coach.sqlite3` (자동 생성, Git 제외)
- 무작위 HttpOnly 쿠키로 브라우저별 데이터를 분리합니다. 로그인 계정 기능은 아닙니다. 쿠키를 삭제하거나 다른 브라우저를 사용하면 이전 기록과 연결되지 않습니다.
- `ENERGY_DB_PATH` 환경변수로 DB 위치를 바꿀 수 있습니다. `.env` 파일을 사용할 경우 실행 명령에 `--env-file .env`를 추가하세요.
- 실제 계측, 월별 청구 이력, IoT 제어 기능은 제공된 코드에 없어 연결하지 않았습니다. 해당 화면에는 데이터 없음 상태를 표시합니다. 미션 토글은 완료 기록입니다.
- 원본의 외부 Tailwind CDN, 글꼴, 배경 이미지는 유지되어 인터넷 연결이 필요합니다.

## 파일 구조

```text
app/main.py                    FastAPI 경로, 요청 모델
app/service.py                 기존 엔진 파이프라인 연결 및 입력 검증
app/store.py                   SQLite 세션 저장
static/energy-coach.js          화면 입력, API 호출, 결과 렌더링
energy-coach.html              기존 디자인과 화면 템플릿
visualstudio_project/src/       기존 엔진 (패키지 import/데이터 경로 수정)
visualstudio_project/data/      기존 설문·규칙·계산·근거 데이터
tests/                         API 및 화면 컨트롤러 테스트
```

## 검증

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests visualstudio_project/tests -q

# 선택: DOM 기반 화면 동작 테스트
npm.cmd ci --ignore-scripts
npm.cmd test
```

API 테스트는 실제 엔진 결과, 입력 검증, 쿠키 격리, SQLite 복원, 미션 저장, 실패 시 기존 결과 보존을 확인합니다. DOM 테스트는 실제 엔진으로 만든 결과를 이용해 전체 화면 이동과 재진단을 확인합니다. 실제 브라우저의 픽셀 단위 시각 검증은 별도 확인이 필요합니다.

구현 참고: [FastAPI 정적 파일 제공](https://fastapi.tiangolo.com/tutorial/static-files/), [FastAPI 테스트](https://fastapi.tiangolo.com/tutorial/testing/).
