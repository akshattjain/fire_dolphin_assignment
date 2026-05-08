"""
Sliding-window code chunker.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data class for a single chunk
# ---------------------------------------------------------------------------

@dataclass
class CodeChunk:
    chunk_type: str   # block
    name: str | None
    start_line: int   # 1-indexed
    end_line: int     # 1-indexed
    content: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(content: str, language: str) -> list[CodeChunk]:
    """
    Parse *content* and return a list of CodeChunk objects using sliding-window chunking.
    """
    return _fallback_chunks(content)

# ---------------------------------------------------------------------------
# Sliding-window chunker
# ---------------------------------------------------------------------------

CHUNK_LINES = 50
OVERLAP_LINES = 10

def _fallback_chunks(content: str) -> list[CodeChunk]:
    """Split content into overlapping line-window blocks."""
    lines = content.splitlines()
    if not lines:
        return []

    chunks: list[CodeChunk] = []
    step = CHUNK_LINES - OVERLAP_LINES
    i = 0
    while i < len(lines):
        end = min(i + CHUNK_LINES, len(lines))
        chunk_lines = lines[i:end]
        chunks.append(
            CodeChunk(
                chunk_type="block",
                name=None,
                start_line=i + 1,
                end_line=end,
                content="\n".join(chunk_lines),
            )
        )
        if end == len(lines):
            break
        i += step

    return chunks
