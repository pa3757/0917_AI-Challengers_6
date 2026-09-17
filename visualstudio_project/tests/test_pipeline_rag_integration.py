from src.rule_engine import evaluate_risks
from src.solution_engine import recommend_solutions
from src.retriever import retrieve_for_solutions


class FakeEmbeddingProvider:
    def embed_query(self, text):
        return [0.1, 0.2]


class FakeCollection:
    def query(self, **kwargs):
        waste_code = kwargs["where"]["waste_code"]
        return {
            "ids": [[f"KB::{waste_code}"]],
            "documents": [[f"근거 문서 for {waste_code}"]],
            "metadatas": [[{
                "knowledge_id": f"KB_{waste_code}",
                "waste_code": waste_code,
                "domain": "test",
                "source_organization": "공식기관",
                "source_document": "공식문서",
                "publication_year": "2026",
                "page": "1",
                "source_url": "https://example.com",
                "source_type": "web",
            }]],
            "distances": [[0.1]],
        }


def test_survey_to_risk_to_solution_to_rag_pipeline():
    answers = {
        "Q01": 80,
        "Q02": 24,
        "Q03": "EMPTY_31_50",
        "Q05": "BOTH_ON",
        "Q06": "OVER_30_MIN",
    }
    risks = evaluate_risks(answers)
    solutions = recommend_solutions(risks)
    grounded = retrieve_for_solutions(
        solutions,
        collection=FakeCollection(),
        embedding_provider=FakeEmbeddingProvider(),
    )
    assert grounded
    assert all(item["rag_grounded"] for item in grounded)
    assert all(item["rag_evidence_count"] == 1 for item in grounded)
