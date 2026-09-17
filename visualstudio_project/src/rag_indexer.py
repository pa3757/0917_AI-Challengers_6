"""Build and validate the persistent ChromaDB index for the RAG knowledge base."""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple, Union

from .embedding_provider import SentenceTransformerEmbeddingProvider


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KB_PATH = PROJECT_ROOT / "data/04_rag/PC방_에너지절감_RAG_Knowledge_Base_v4.csv"
DEFAULT_SOLUTION_PATH = PROJECT_ROOT / "data/03_solution/solution_catalog.csv"
DEFAULT_CHROMA_PATH = PROJECT_ROOT / "chroma_db"
DEFAULT_COLLECTION_NAME = os.getenv("RAG_COLLECTION_NAME", "pcbang_energy_rag")

REQUIRED_COLUMNS = {
    "knowledge_id",
    "domain",
    "waste_code",
    "problem",
    "recommended_action",
    "evidence",
    "source_organization",
    "source_document",
    "publication_year",
    "page",
    "source_url",
    "source_type",
}


def split_waste_codes(value: str) -> List[str]:
    """Split a semicolon-delimited waste_code field into unique codes."""
    seen = set()
    codes: List[str] = []
    for raw in (value or "").split(";"):
        code = raw.strip()
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def load_knowledge_base(path: Union[str, Path] = DEFAULT_KB_PATH) -> List[Dict[str, str]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"RAG knowledge base not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            raise ValueError(f"RAG knowledge base missing columns: {sorted(missing)}")
        rows = [dict(row) for row in reader]

    knowledge_ids = [row["knowledge_id"].strip() for row in rows]
    if any(not kid for kid in knowledge_ids):
        raise ValueError("knowledge_id must not be blank")
    if len(knowledge_ids) != len(set(knowledge_ids)):
        raise ValueError("knowledge_id values must be unique")
    return rows


def build_document(row: Dict[str, str]) -> str:
    """Construct the exact text that will be embedded for semantic retrieval."""
    parts = [
        f"분야: {row.get('domain', '').strip()}",
        f"문제 상황: {row.get('problem', '').strip()}",
        f"권장 조치: {row.get('recommended_action', '').strip()}",
        f"공식 근거: {row.get('evidence', '').strip()}",
        f"출처 기관: {row.get('source_organization', '').strip()}",
        f"출처 문서: {row.get('source_document', '').strip()}",
    ]
    return "\n".join(part for part in parts if part.split(":", 1)[-1].strip())


def _clean_metadata_value(value: Any) -> str | int | float | bool:
    # Chroma metadata must be scalar and cannot be None.
    if isinstance(value, (bool, int, float)):
        return value
    return "" if value is None else str(value)


def build_metadata(row: Dict[str, str], waste_code: str) -> Dict[str, str | int | float | bool]:
    return {
        "knowledge_id": _clean_metadata_value(row.get("knowledge_id", "")),
        "domain": _clean_metadata_value(row.get("domain", "")),
        "waste_code": waste_code,
        "source_organization": _clean_metadata_value(row.get("source_organization", "")),
        "source_document": _clean_metadata_value(row.get("source_document", "")),
        "publication_year": _clean_metadata_value(row.get("publication_year", "")),
        "page": _clean_metadata_value(row.get("page", "")),
        "source_url": _clean_metadata_value(row.get("source_url", "")),
        "source_type": _clean_metadata_value(row.get("source_type", "")),
    }


def expand_knowledge_rows(rows: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Expand multi-code rows so Chroma can filter by one exact waste_code.

    A CSV row such as ``A;B`` is indexed twice with the same document but distinct
    vector IDs. This avoids fragile substring matching in Chroma metadata filters.
    """
    expanded: List[Dict[str, Any]] = []
    ids = set()
    for row in rows:
        codes = split_waste_codes(row.get("waste_code", ""))
        if not codes:
            raise ValueError(f"No waste_code for knowledge_id={row.get('knowledge_id')}")
        document = build_document(row)
        if not document.strip():
            raise ValueError(f"Empty embedding document for knowledge_id={row.get('knowledge_id')}")
        for code in codes:
            vector_id = f"{row['knowledge_id']}::{code}"
            if vector_id in ids:
                raise ValueError(f"Duplicate vector id: {vector_id}")
            ids.add(vector_id)
            expanded.append(
                {
                    "id": vector_id,
                    "document": document,
                    "metadata": build_metadata(row, code),
                }
            )
    return expanded


def load_solution_waste_codes(path: Union[str, Path] = DEFAULT_SOLUTION_PATH) -> List[str]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [row["waste_code"].strip() for row in csv.DictReader(f) if row.get("waste_code", "").strip()]


def validate_solution_coverage(
    kb_path: Union[str, Path] = DEFAULT_KB_PATH,
    solution_path: Union[str, Path] = DEFAULT_SOLUTION_PATH,
) -> Dict[str, Any]:
    rows = load_knowledge_base(kb_path)
    kb_codes = {code for row in rows for code in split_waste_codes(row["waste_code"])}
    solution_codes = set(load_solution_waste_codes(solution_path))
    missing = sorted(solution_codes - kb_codes)
    return {
        "solution_waste_code_count": len(solution_codes),
        "kb_waste_code_count": len(kb_codes),
        "missing_waste_codes": missing,
        "coverage_complete": not missing,
    }


def _get_chroma_client(persist_directory: Union[str, Path]):
    try:
        import chromadb
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "chromadb is required to build the persistent RAG index. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from exc
    Path(persist_directory).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_directory))


def build_chroma_index(
    kb_path: Union[str, Path] = DEFAULT_KB_PATH,
    persist_directory: Union[str, Path] = DEFAULT_CHROMA_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_provider: Any | None = None,
    reset: bool = False,
    batch_size: int = 64,
) -> Dict[str, Any]:
    """Create/update the persistent Chroma index from the CSV source of truth."""
    rows = load_knowledge_base(kb_path)
    records = expand_knowledge_rows(rows)
    coverage = validate_solution_coverage(kb_path=kb_path)
    if not coverage["coverage_complete"]:
        raise ValueError(
            "RAG KB does not cover all solution waste_codes: "
            + ", ".join(coverage["missing_waste_codes"])
        )

    provider = embedding_provider or SentenceTransformerEmbeddingProvider()
    client = _get_chroma_client(persist_directory)

    if reset:
        try:
            client.delete_collection(collection_name)
        except Exception:
            # Collection may not exist yet. Avoid depending on Chroma-version-specific exceptions.
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "PC방 에너지 누수 공식근거 RAG", "hnsw:space": "cosine"},
    )

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        documents = [item["document"] for item in batch]
        embeddings = provider.embed_documents(documents)
        if len(embeddings) != len(batch):
            raise ValueError("Embedding provider returned an unexpected number of vectors")
        collection.upsert(
            ids=[item["id"] for item in batch],
            documents=documents,
            metadatas=[item["metadata"] for item in batch],
            embeddings=embeddings,
        )

    return {
        "source_rows": len(rows),
        "indexed_vectors": len(records),
        "collection_name": collection_name,
        "persist_directory": str(Path(persist_directory)),
        **coverage,
    }
