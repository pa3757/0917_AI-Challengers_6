from src.retriever import retrieve_evidence, retrieve_for_solution


class FakeEmbeddingProvider:
    def embed_query(self, text):
        assert text
        return [0.1, 0.2, 0.3]


class FakeCollection:
    def __init__(self):
        self.last_query = None

    def query(self, **kwargs):
        self.last_query = kwargs
        return {
            "ids": [["K1::PC_IDLE_WINDOW_LEAK"]],
            "documents": [["official evidence document"]],
            "metadatas": [[{
                "knowledge_id": "K1",
                "waste_code": "PC_IDLE_WINDOW_LEAK",
                "domain": "PC·모니터",
                "source_organization": "한국에너지공단",
                "source_document": "가이드",
                "publication_year": "2026",
                "page": "1",
                "source_url": "https://example.com",
                "source_type": "PDF",
            }]],
            "distances": [[0.12]],
        }


def test_retrieval_uses_exact_waste_code_filter():
    collection = FakeCollection()
    results = retrieve_evidence(
        "PC_IDLE_WINDOW_LEAK",
        "빈 좌석 PC 절전",
        top_k=3,
        collection=collection,
        embedding_provider=FakeEmbeddingProvider(),
    )
    assert collection.last_query["where"] == {"waste_code": "PC_IDLE_WINDOW_LEAK"}
    assert collection.last_query["n_results"] == 3
    assert results[0]["knowledge_id"] == "K1"
    assert results[0]["distance"] == 0.12


def test_solution_retrieval_keeps_solution_and_grounding_state():
    collection = FakeCollection()
    solution = {
        "solution_id": "SOL_PC_003",
        "waste_code": "PC_IDLE_WINDOW_LEAK",
        "solution_name": "자동 절전 전환시간 최적화",
        "rag_query": "컴퓨터 자동 절전 대기전력",
    }
    result = retrieve_for_solution(
        solution,
        collection=collection,
        embedding_provider=FakeEmbeddingProvider(),
    )
    assert result["solution_id"] == "SOL_PC_003"
    assert result["rag_grounded"] is True
    assert result["rag_evidence_count"] == 1
    assert result["rag_query_used"] == solution["rag_query"]


class EmptyCollection:
    def query(self, **kwargs):
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


def test_missing_exact_evidence_does_not_fallback_to_unrelated_documents():
    result = retrieve_for_solution(
        {
            "solution_id": "X",
            "waste_code": "NO_SUCH_CODE",
            "solution_name": "unknown",
            "rag_query": "unknown",
        },
        collection=EmptyCollection(),
        embedding_provider=FakeEmbeddingProvider(),
    )
    assert result["rag_evidence"] == []
    assert result["rag_grounded"] is False
