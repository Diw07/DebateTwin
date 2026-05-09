"""
rag/ingest.py
-------------
CLI utility to ingest persona documents into ChromaDB.

Usage
-----
    python -m rag.ingest --file ../data/personas/my_bio.txt --persona default
    python -m rag.ingest --file ../data/uploads/resume.pdf --persona alice
"""

import argparse
import sys
from pathlib import Path

# Ensure backend root is on PYTHONPATH when run as __main__
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.memory import get_memory
from utils import get_logger

logger = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest a document into the Debate Twin persona store."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to a .txt or .pdf file to ingest.",
    )
    parser.add_argument(
        "--persona",
        default="default",
        help="Persona ID to associate this document with (default: 'default').",
    )
    args = parser.parse_args()

    memory = get_memory()
    try:
        count = memory.ingest_file(args.file, persona_id=args.persona)
        print(f"✅  Ingested {count} chunks from '{args.file}' → persona='{args.persona}'")
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"❌  Ingestion failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
