# RAG / ChromaDB 단계 상태

## 구현 완료

- CSV 원본: `data/04_rag/PC방_에너지절감_RAG_Knowledge_Base_v4.csv`
- 45개 Knowledge Row
- Solution Engine에서 사용하는 15개 `waste_code` 모두 RAG 근거 커버
- 다중 `waste_code` 행은 인덱싱 시 개별 메타데이터 레코드로 확장
- Persistent ChromaDB 인덱서: `src/rag_indexer.py`
- OpenAI Embedding provider: `src/embedding_provider.py`
- `waste_code` exact metadata filter + semantic Top-k Retriever: `src/retriever.py`
- 인덱스 생성 CLI: `scripts/build_rag_index.py`
- 테스트: `test_rag_indexer.py`, `test_retriever.py`, `test_pipeline_rag_integration.py`

## 중요한 설계 원칙

1. `RAG_Knowledge_Base.csv`가 사람이 관리하는 Source of Truth이다.
2. ChromaDB는 CSV를 임베딩한 검색 인덱스다.
3. 검색은 먼저 `waste_code`로 정확히 필터링한 뒤, 그 범위 안에서 semantic Top-k를 수행한다.
4. 정확한 `waste_code` 근거가 없을 때 전체 KB에서 비슷한 문서를 임의 fallback하지 않는다.
5. Calculation Reference DB는 ChromaDB에 넣지 않는다. 수치 계산은 Python이 정확한 key/parameter로 조회한다.
6. RAG는 공식 근거 설명에만 사용하며 Risk Score나 절감량을 결정하지 않는다.

## KB v4 변경점

v3에서 Solution Engine의 `REFRIG_DEFROST_CONTROL`에 대응하는 Knowledge Row가 없어서 v4에 1개를 추가했다.
공식 근거는 한국에너지공단 EG-TIPS 우수절감기술 목록의 `쇼케이스 제상히터 최적 제어` 항목이다.
고정 절감률이나 임의 제상주기는 추가하지 않았다.

## 로컬 실행 순서

```bash
pip install -r requirements.txt
```

프로젝트 루트에 `.env` 파일을 만들고:

```text
OPENAI_API_KEY=YOUR_KEY
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
RAG_COLLECTION_NAME=pcbang_energy_rag
```

인덱스 생성:

```bash
python scripts/build_rag_index.py --reset
```

테스트:

```bash
pytest -q
```

## 현재 검증 상태

현재 작업 환경에는 `chromadb` 패키지를 인터넷에서 설치할 수 없어 실제 PersistentClient 생성과 OpenAI Embedding API 호출은 실행하지 못했다.
대신 Chroma 의존성을 지연 import로 분리하고, fake collection / fake embedding provider를 사용해 인덱싱 전처리·정확한 waste_code 필터·retrieval output·전체 파이프라인 연결을 단위 테스트했다.
