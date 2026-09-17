"""RAG retrieval using persistent ChromaDB and exact waste_code filtering."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence, Union

from .embedding_provider import SentenceTransformerEmbeddingProvider
from .rag_indexer import DEFAULT_CHROMA_PATH, DEFAULT_COLLECTION_NAME


def _get_collection(
    persist_directory: Union[str, Path] = DEFAULT_CHROMA_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
):
    try:
        import chromadb
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "chromadb is required for RAG retrieval. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc
    client = chromadb.PersistentClient(path=str(persist_directory))
    try:
        return client.get_collection(collection_name)
    except Exception as exc:
        raise RuntimeError(
            f"RAG collection '{collection_name}' was not found. "
            "Run scripts/build_rag_index.py first."
        ) from exc


def _normalize_query_result(raw: Dict[str, Any], waste_code: str) -> List[Dict[str, Any]]:
    ids = (raw.get("ids") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]

    output: List[Dict[str, Any]] = []
    for idx, vector_id in enumerate(ids):
        metadata = metadatas[idx] if idx < len(metadatas) and metadatas[idx] else {}
        document = documents[idx] if idx < len(documents) else None
        distance = distances[idx] if idx < len(distances) else None
        output.append(
            {
                "rank": idx + 1,
                "vector_id": vector_id,
                "knowledge_id": metadata.get("knowledge_id"),
                "waste_code": metadata.get("waste_code", waste_code),
                "domain": metadata.get("domain"),
                "document": document,
                "distance": distance,
                "source_organization": metadata.get("source_organization"),
                "source_document": metadata.get("source_document"),
                "publication_year": metadata.get("publication_year"),
                "page": metadata.get("page"),
                "source_url": metadata.get("source_url"),
                "source_type": metadata.get("source_type"),
            }
        )
    return output


def retrieve_evidence(
    waste_code: str,
    query: str,
    top_k: int = 3,
    *,
    collection: Any | None = None,
    embedding_provider: Any | None = None,
    persist_directory: Union[str, Path] = DEFAULT_CHROMA_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> List[Dict[str, Any]]:
    """Retrieve official evidence for one diagnosed waste_code.

    Retrieval deliberately requires an exact waste_code metadata filter. It does
    not fall back to global semantic search, because unrelated official evidence
    should not be attached to a diagnosis just because its wording is similar.
    """
    if not waste_code or not waste_code.strip():
        raise ValueError("waste_code is required")
    if not query or not query.strip():
        query = waste_code
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    provider = embedding_provider if embedding_provider is not None else SentenceTransformerEmbeddingProvider()
    collection = collection if collection is not None else _get_collection(persist_directory, collection_name)
    query_embedding = provider.embed_query(query)
    raw = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"waste_code": waste_code},
        include=["documents", "metadatas", "distances"],
    )
    return _normalize_query_result(raw, waste_code)


def retrieve_for_solution(
    solution: Dict[str, Any],
    top_k: int = 3,
    **kwargs: Any,
) -> Dict[str, Any]:
    waste_code = solution.get("waste_code", "")
    query = solution.get("rag_query") or solution.get("solution_name") or waste_code
    evidence = retrieve_evidence(waste_code=waste_code, query=query, top_k=top_k, **kwargs)
    return {
        **solution,
        "rag_query_used": query,
        "rag_evidence": evidence,
        "rag_evidence_count": len(evidence),
        "rag_grounded": bool(evidence),
    }


def retrieve_for_solutions(
    solutions: Sequence[Dict[str, Any]],
    top_k: int = 3,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    return [retrieve_for_solution(solution, top_k=top_k, **kwargs) for solution in solutions]
