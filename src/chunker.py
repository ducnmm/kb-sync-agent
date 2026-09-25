"""Chunking utility module for text normalization and chunk counting."""

import re
from typing import List


def estimate_token_count(text: str) -> int:
    """
    Estimate token count for a given text.
    Standard rule of thumb: ~4 characters per token in English.
    """
    if not text:
        return 0
    words = re.findall(r"\S+", text)
    # Average ~1.3 tokens per word, or len(text)/4
    return max(1, int(len(text) / 4))


def chunk_markdown(
    text: str,
    max_chunk_tokens: int = 800,
    overlap_tokens: int = 100,
) -> List[str]:
    """
    Chunk markdown text while respecting paragraph/section boundaries.
    
    Rationale:
    - 800 tokens (~3200 chars) comfortably encapsulates whole instructional steps
      (e.g., configuring YouTube settings, adding a screen) without fragmenting procedures.
    - 100 tokens (~400 chars) overlap preserves continuity across section transitions.
    """
    if not text.strip():
        return []

    # Split into paragraphs to maintain semantic cohesion
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_token_count(para)

        # If a single paragraph exceeds the chunk limit, split it by lines or sentences
        if para_tokens > max_chunk_tokens:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_tokens = 0

            lines = para.split("\n")
            sub_chunk = []
            sub_tokens = 0
            for line in lines:
                l_tokens = estimate_token_count(line)
                if sub_tokens + l_tokens > max_chunk_tokens and sub_chunk:
                    chunks.append("\n".join(sub_chunk))
                    sub_chunk = [line]
                    sub_tokens = l_tokens
                else:
                    sub_chunk.append(line)
                    sub_tokens += l_tokens
            if sub_chunk:
                chunks.append("\n".join(sub_chunk))
            continue

        if current_tokens + para_tokens > max_chunk_tokens and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            # Start new chunk with overlap if possible
            overlap_acc = []
            overlap_count = 0
            for prev_para in reversed(current_chunk):
                p_tok = estimate_token_count(prev_para)
                if overlap_count + p_tok <= overlap_tokens:
                    overlap_acc.insert(0, prev_para)
                    overlap_count += p_tok
                else:
                    break
            current_chunk = overlap_acc + [para]
            current_tokens = overlap_count + para_tokens
        else:
            current_chunk.append(para)
            current_tokens += para_tokens

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks if chunks else [text]
