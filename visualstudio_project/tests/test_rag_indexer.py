import csv
from pathlib import Path

from src.rag_indexer import (
    build_document,
    expand_knowledge_rows,
    load_knowledge_base,
    split_waste_codes,
    validate_solution_coverage,
)


def test_split_waste_codes_handles_multi_code_rows():
    assert split_waste_codes("PC_OFF_STANDBY_LEAK;PERIPHERAL_IDLE_POWER") == [
        "PC_OFF_STANDBY_LEAK",
        "PERIPHERAL_IDLE_POWER",
    ]


def test_rag_kb_has_required_content():
    rows = load_knowledge_base()
    assert len(rows) >= 45
    assert all(row["knowledge_id"] for row in rows)
    assert all(row["evidence"] for row in rows)
    assert all(row["source_url"] for row in rows)


def test_embedding_document_keeps_evidence_and_action():
    row = load_knowledge_base()[0]
    doc = build_document(row)
    assert row["recommended_action"] in doc
    assert row["evidence"] in doc
    assert row["source_organization"] in doc


def test_expanded_rows_use_exact_single_waste_code_metadata():
    rows = [
        {
            "knowledge_id": "K1",
            "domain": "test",
            "waste_code": "A;B",
            "problem": "problem",
            "recommended_action": "action",
            "evidence": "evidence",
            "source_organization": "org",
            "source_document": "doc",
            "publication_year": "2026",
            "page": "1",
            "source_url": "https://example.com",
            "source_type": "web",
        }
    ]
    expanded = expand_knowledge_rows(rows)
    assert [x["metadata"]["waste_code"] for x in expanded] == ["A", "B"]
    assert len({x["id"] for x in expanded}) == 2


def test_every_solution_waste_code_has_rag_coverage():
    coverage = validate_solution_coverage()
    assert coverage["coverage_complete"] is True
    assert coverage["missing_waste_codes"] == []
