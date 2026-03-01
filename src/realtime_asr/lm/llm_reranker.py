from __future__ import annotations

import json
import re
import time
from typing import Iterable


class LocalLLMReranker:
    """Optional local LLM-based reranker using llama-cpp-python.

    Requires a local GGUF instruct model path.
    """

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 2048,
        max_tokens: int = 220,
        temperature: float = 0.0,
    ) -> None:
        try:
            from llama_cpp import Llama
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "llama-cpp-python is required for --llm-model mode. "
                "Install with: pip install 'realtime-asr[llm]'"
            ) from exc

        self._llm = Llama(model_path=model_path, n_ctx=n_ctx, verbose=False)
        self.max_tokens = max_tokens
        self.temperature = temperature

    def suggest_scores(
        self,
        texts: Iterable[str],
        base_terms: dict[str, float],
        top_k: int = 30,
    ) -> dict[str, float]:
        prompt = self._build_prompt(texts=texts, base_terms=base_terms, top_k=top_k)
        started = time.time()
        output = self._llm(
            prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stop=["```", "\n\n"],
        )
        _elapsed = time.time() - started
        text = output["choices"][0]["text"]
        return self._parse_json_scores(text)

    def _build_prompt(
        self,
        texts: Iterable[str],
        base_terms: dict[str, float],
        top_k: int,
    ) -> str:
        snippet = "\n".join([t.strip() for t in texts if t.strip()][-8:])
        ranked = sorted(base_terms.items(), key=lambda x: x[1], reverse=True)[:40]
        ranked_str = ", ".join([f"{t}:{s:.2f}" for t, s in ranked])

        return (
            "You are a keyword extraction assistant.\n"
            "Task: from transcript text, return high-signal topic words/short phrases.\n"
            "Avoid pronouns, modal verbs, filler words, and generic helper words.\n"
            "Prefer concrete topical nouns and 2-word phrases.\n"
            f"Return strict JSON array only, max {top_k} items, each item as {{\"term\": string, \"score\": number 0..1}}.\n"
            "\n"
            "Transcript:\n"
            f"{snippet}\n"
            "\n"
            "Current ranked candidates:\n"
            f"{ranked_str}\n"
            "\n"
            "JSON:\n"
        )

    def _parse_json_scores(self, text: str) -> dict[str, float]:
        candidate = text.strip()
        # Try to isolate first JSON array block if model adds noise.
        if not candidate.startswith("["):
            m = re.search(r"\[[\s\S]*\]", candidate)
            if m:
                candidate = m.group(0)

        try:
            data = json.loads(candidate)
        except Exception:
            return {}
        if not isinstance(data, list):
            return {}

        scores: dict[str, float] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            term = str(item.get("term", "")).strip().lower()
            if not term:
                continue
            try:
                score = float(item.get("score", 0.0))
            except Exception:
                continue
            if score <= 0:
                continue
            if score > 1.0:
                score = 1.0
            scores[term] = max(scores.get(term, 0.0), score)
        return scores
