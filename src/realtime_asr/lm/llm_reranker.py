from __future__ import annotations

import json
import os
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
        chat_format: str | None = "chatml",
    ) -> None:
        try:
            from llama_cpp import Llama
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "llama-cpp-python is required for --llm-model mode. "
                "Install with: pip install 'realtime-asr[llm]'"
            ) from exc

        self._llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            verbose=False,
            chat_format=chat_format,
        )
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

        # Instruct models tend to behave better through chat-style prompting.
        text = ""
        try:
            output = self._llm.create_chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You extract high-signal topic terms from transcripts. "
                            "Return JSON only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            text = output["choices"][0]["message"]["content"] or ""
        except Exception:
            output = self._llm(
                "<|im_start|>system\nYou extract high-signal topic terms from transcripts. Return JSON only.<|im_end|>\n"
                "<|im_start|>user\n"
                + prompt
                + "<|im_end|>\n"
                "<|im_start|>assistant\n",
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stop=None,
            )
            text = output["choices"][0]["text"]

        _elapsed = time.time() - started
        scores = self._parse_json_scores(text)
        if not scores:
            scores = self._parse_loose_scores(text)
        self._maybe_dump_debug(prompt, text, scores)
        return scores

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
            f"Return strict JSON array ONLY, max {top_k} items, each item as {{\"term\": string, \"score\": number 0..1}}.\n"
            "Do not include markdown, explanation, or any extra text.\n"
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
        if candidate.startswith("```"):
            candidate = re.sub(r"^```[a-zA-Z]*\n?", "", candidate).strip()
            candidate = re.sub(r"\n?```$", "", candidate).strip()
        # Try to isolate first JSON array block if model adds noise.
        if not candidate.startswith("["):
            m = re.search(r"\[[\s\S]*\]", candidate)
            if m:
                candidate = m.group(0)

        try:
            data = json.loads(candidate)
        except Exception:
            # Try object wrapper: {"terms":[...]}.
            try:
                obj = json.loads(text)
                data = obj.get("terms", []) if isinstance(obj, dict) else []
            except Exception:
                data = []
        if not isinstance(data, list):
            data = []

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
        if scores:
            return scores

        # Recover from truncated JSON by extracting term/score pairs directly.
        for m in re.finditer(
            r'"term"\s*:\s*"([^"]+)"\s*,\s*"score"\s*:\s*(0(?:\.\d+)?|1(?:\.0+)?)',
            text,
            flags=re.IGNORECASE,
        ):
            term = m.group(1).strip().lower()
            if not term:
                continue
            score = float(m.group(2))
            scores[term] = max(scores.get(term, 0.0), score)
        return scores

    def _parse_loose_scores(self, text: str) -> dict[str, float]:
        # Fallback parser for lines like:
        # - machine learning: 0.92
        # machine learning - 0.92
        scores: dict[str, float] = {}
        for line in text.splitlines():
            m = re.search(r"^\s*[-*]?\s*([a-zA-Z][a-zA-Z0-9 \-']{2,80}?)\s*[:\-]\s*(0(?:\.\d+)?|1(?:\.0+)?)\s*$", line.strip())
            if not m:
                continue
            term = m.group(1).strip().lower()
            score = float(m.group(2))
            scores[term] = max(scores.get(term, 0.0), score)
        return scores

    def _maybe_dump_debug(self, prompt: str, raw_text: str, scores: dict[str, float]) -> None:
        if os.getenv("COTVIS_LLM_DEBUG") != "1":
            return
        try:
            with open("/tmp/cotvis_llm_debug.txt", "w", encoding="utf-8") as f:
                f.write("=== PROMPT ===\n")
                f.write(prompt)
                f.write("\n\n=== RAW OUTPUT ===\n")
                f.write(raw_text or "<empty>")
                f.write("\n\n=== PARSED SCORES ===\n")
                f.write(json.dumps(scores, ensure_ascii=False, indent=2))
        except Exception:
            pass
