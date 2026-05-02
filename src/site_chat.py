"""Ask-the-Audit: a small RAG Q&A interface over the audited site's content.

Usage:
    # Simple one-shot question
    python -m src.site_chat "What does our site say about activation rate benchmarks?"

    # JSON output (for the dashboard's Ask tab to consume)
    python -m src.site_chat --json "How do we differentiate from competitors on attribution?"

The pipeline already produces a FAISS index of every page chunk during clustering.
This module reuses that index — same artifact does double duty (cluster discovery
during the audit, RAG retrieval during day-to-day operations).

Pipeline:
  1. embed the question
  2. retrieve top-k chunks via the shared RetrievalIndex
  3. assemble a context window with [N] citation tags
  4. ask Claude to answer using ONLY the retrieved context
  5. return answer + the cited source URLs
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass

from src.retrieval import Chunk, get_index

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an SEO + content strategy analyst answering a question \
about the user's own website using ONLY the retrieved context below.

Rules:
- Ground every claim in the context. If the context doesn't answer the question, \
  say so plainly — do not guess.
- Cite the source by [N] (matching the numbered context blocks). Multiple \
  citations welcome.
- Keep the answer tight: 2-4 short paragraphs max.
- If multiple pages contradict each other, surface the contradiction explicitly.
- Always end with a 1-line "What this means for your content strategy" takeaway."""


@dataclass
class Answer:
    question: str
    answer: str
    citations: list  # list of {n, url, snippet}
    used_chunks: int

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": self.citations,
            "used_chunks": self.used_chunks,
        }


def _format_context(chunks: list[Chunk]) -> tuple[str, list]:
    """Return (context_block_for_prompt, citation_metadata)."""
    blocks = []
    citations = []
    for i, c in enumerate(chunks, start=1):
        text = c.short(900)
        blocks.append(f"[{i}] {c.url}\n{text}")
        citations.append({"n": i, "url": c.url, "snippet": text[:200]})
    return "\n\n".join(blocks), citations


def ask(question: str, k: int = 6) -> Answer:
    """Ask one question. Returns an Answer with cited sources."""
    if not question or not question.strip():
        return Answer(question=question, answer="(empty question)", citations=[], used_chunks=0)

    idx = get_index()
    if idx is None:
        return Answer(
            question=question,
            answer="No retrieval index available. Run the audit pipeline first to populate cache/.",
            citations=[],
            used_chunks=0,
        )

    chunks = idx.search_by_text(question, k=k)
    if not chunks:
        return Answer(
            question=question,
            answer="No relevant content found in the audited site for this question.",
            citations=[],
            used_chunks=0,
        )

    context, citations = _format_context(chunks)

    # Use the shared LLM advisor for the call (handles enable/disable cleanly)
    from src import llm_advisor
    if not llm_advisor.is_enabled():
        # Auto-enable for one-off Q&A if env var is set
        llm_advisor.enable_for_session()
    if not llm_advisor.is_enabled():
        return Answer(
            question=question,
            answer="LLM disabled (set ANTHROPIC_API_KEY + run with --use-llm). Retrieved chunks are in citations.",
            citations=citations,
            used_chunks=len(chunks),
        )

    user_msg = f"Question: {question}\n\nRetrieved context:\n\n{context}"
    response_text = llm_advisor.raw_completion(
        system=SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=900,
    ) or ""

    return Answer(
        question=question,
        answer=response_text.strip(),
        citations=citations,
        used_chunks=len(chunks),
    )


def main():
    parser = argparse.ArgumentParser(description="Ask a question about the audited site (RAG over the FAISS index).")
    parser.add_argument("question", nargs="?", help="The question to ask. If omitted, reads from stdin.")
    parser.add_argument("--k", type=int, default=6, help="Number of chunks to retrieve (default 6).")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of pretty text.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    question = args.question or sys.stdin.read().strip()
    if not question:
        parser.error("No question provided.")

    ans = ask(question, k=args.k)

    if args.json:
        print(json.dumps(ans.to_dict(), indent=2))
        return

    print()
    print("Q:", question)
    print()
    print(ans.answer)
    print()
    if ans.citations:
        print(f"Sources ({ans.used_chunks} chunks):")
        for c in ans.citations:
            print(f"  [{c['n']}] {c['url']}")


if __name__ == "__main__":
    main()
