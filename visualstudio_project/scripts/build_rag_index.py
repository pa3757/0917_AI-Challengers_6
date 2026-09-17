from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag_indexer import build_chroma_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build persistent ChromaDB index for the PC방 RAG KB")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate the collection")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    result = build_chroma_index(reset=args.reset, batch_size=args.batch_size)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
