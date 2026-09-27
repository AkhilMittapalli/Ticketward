"""Rebuild knowledge-base chunks, embeddings and the BM25 index (planned in P5; spec §8.4).

Runs after an embedding-model change (with a migration, ADR-0008) or a bulk KB import.
Not implemented in P0.
"""

import sys

if __name__ == "__main__":
    sys.exit("reindex.py: not implemented yet - planned in P5 (retrieval)")
