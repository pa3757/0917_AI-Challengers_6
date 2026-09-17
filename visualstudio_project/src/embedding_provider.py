
"""Embedding providers used by the RAG layer."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Sequence

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass


class SentenceTransformerEmbeddingProvider:
    """Free local multilingual embedding provider."""

    def __init__(
        self,
        model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    ) -> None:
        self.model_name = model
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            print(f"Embedding model loading: {self.model_name}")

            self._model = SentenceTransformer(
                self.model_name
            )

        return self._model

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> List[List[float]]:

        if not texts:
            return []

        model = self._get_model()

        embeddings = model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        return embeddings.tolist()

    def embed_query(
        self,
        text: str,
    ) -> List[float]:

        return self.embed_documents([text])[0]


class OpenAIEmbeddingProvider:
    """Optional OpenAI embedding provider."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:

        self.model = model or os.getenv(
            "OPENAI_EMBEDDING_MODEL",
            "text-embedding-3-small",
        )

        self.api_key = api_key or os.getenv(
            "OPENAI_API_KEY"
        )

        self._client = None

    def _get_client(self):

        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set."
            )

        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key
            )

        return self._client

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> List[List[float]]:

        if not texts:
            return []

        client = self._get_client()

        response = client.embeddings.create(
            model=self.model,
            input=list(texts),
        )

        ordered = sorted(
            response.data,
            key=lambda item: item.index,
        )

        return [
            item.embedding
            for item in ordered
        ]

    def embed_query(
        self,
        text: str,
    ) -> List[float]:

        return self.embed_documents([text])[0]
