"""Evaluator — VLM screenshot review + text self-review."""

from __future__ import annotations

from io import BytesIO
import json
import logging
import re
from typing import Any

from nsdn.llm import LLMProvider
from nsdn.newspaper import prompts

logger = logging.getLogger(__name__)


class Evaluator:
    """Evaluates designed pages using text self-review + VLM screenshot review."""

    def __init__(
        self,
        design_llm: LLMProvider,
        evaluate_llm: LLMProvider | None = None,
        config: dict | None = None,
    ):
        self.design_llm = design_llm
        self.evaluate_llm = evaluate_llm or design_llm
        self.config = config or {}
        weights = self.config.get("evaluation", {})
        self.text_weight = weights.get("text_weight", 0.3)
        self.vlm_weight = weights.get("vlm_weight", 0.7)

    def evaluate(self, screenshot: bytes, layout_spec: str, topic: str) -> tuple[float, str]:
        """Evaluate a designed page.

        Args:
            screenshot: PNG bytes of the rendered page.
            layout_spec: JSON layout spec from the generator.
            topic: Topic name for context.

        Returns:
            (score, critique) — combined score and actionable critique.
        """
        text_score, text_critique = self._evaluate_text(layout_spec)
        vlm_score, vlm_critique = self._evaluate_vlm(screenshot, topic)

        final_score = (text_score * self.text_weight) + (vlm_score * self.vlm_weight)
        critique = f"Text review ({text_score:.1f}/10): {text_critique}\n\nVLM review ({vlm_score:.1f}/10): {vlm_critique}"
        return final_score, critique

    def _evaluate_text(self, layout_spec: str) -> tuple[float, str]:
        """Evaluate the JSON layout spec."""
        user_prompt = prompts.build_evaluate_text_prompt(layout_spec)
        try:
            response = self.design_llm.invoke(user_prompt, system_message=prompts.EVALUATE_TEXT_SYSTEM_PROMPT, temperature=0.0)
            score = self._parse_score(response)
            return score, response
        except Exception as exc:
            logger.warning("Text evaluation failed: %s", exc)
            return 4.0, f"Evaluation failed: {exc}"

    def _evaluate_vlm(self, screenshot: bytes, topic: str) -> tuple[float, str]:
        """Evaluate the rendered screenshot via VLM.

        For multimodal models, this would pass the image.
        For text-only models, we fall back to evaluating the HTML description.
        """
        # Check if the LLM supports multimodal input
        # For now, we use a text-based fallback that describes the screenshot
        # In production, the evaluate_llm would be a multimodal model (e.g., gemma4-e4b)
        try:
            # Attempt multimodal evaluation
            return self._evaluate_vlm_multimodal(screenshot, topic)
        except Exception as exc:
            logger.info("VLM multimodal evaluation not available, using text fallback: %s", exc)
            return 4.0, "VLM evaluation not available (multimodal model required)"

    def _evaluate_vlm_multimodal(self, screenshot: bytes, topic: str) -> tuple[float, str]:
        """Attempt multimodal VLM evaluation.

        Uses base64 data URI for LlamaServerProvider (file:// is blocked by default).
        Supports LlamaServerProvider (OpenAI-compatible API) and OllamaProvider.
        """
        if self.evaluate_llm is None:
            raise ValueError("No evaluate LLM configured")

        import base64
        from nsdn.llm import LlamaServerProvider, OllamaProvider

        user_prompt = f"Topic: {topic}\n\nEvaluate this newspaper page screenshot."

        if isinstance(self.evaluate_llm, LlamaServerProvider):
            normalized = self._prepare_image_for_llama_server(screenshot)
            image_b64 = base64.b64encode(normalized).decode("utf-8")
            resp = self.evaluate_llm.client.chat.completions.create(
                model=self.evaluate_llm.model,
                messages=[
                    {
                        "role": "system",
                        "content": prompts.EVALUATE_VLM_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                        ],
                    }
                ],
                temperature=0.6,
            )
            content = resp.choices[0].message.content
        elif isinstance(self.evaluate_llm, OllamaProvider):
            resp = self.evaluate_llm.client.chat(
                model=self.evaluate_llm.model,
                messages=[
                    {"role": "system", "content": prompts.EVALUATE_VLM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                images=[screenshot],
                options={"temperature": 0.6},
            )
            content = resp.message.content  # type: ignore[union-attr]
        else:
            raise ValueError(
                f"Multimodal evaluation not supported for provider: {type(self.evaluate_llm).__name__}"
            )

        score = self._parse_score(content)
        return score, content

    @staticmethod
    def _prepare_image_for_llama_server(image_bytes: bytes) -> bytes:
        """Normalize screenshot to safer Gemma4V input (~768x768 RGB JPEG)."""
        try:
            from PIL import Image, ImageOps
        except Exception:
            return image_bytes

        with Image.open(BytesIO(image_bytes)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img = ImageOps.pad(
                img,
                (768, 768),
                method=Image.Resampling.LANCZOS,
                color=(255, 255, 255),
            )
            out = BytesIO()
            img.save(out, format="JPEG", quality=90, optimize=True)
            return out.getvalue()

    @staticmethod
    def _parse_score(text: str) -> float:
        """Extract a score from LLM response."""
        text = text.strip()
        # Try direct float
        try:
            val = float(text[:3])
            return max(1.0, min(10.0, val))
        except ValueError:
            pass
        # Try to find a number
        match = re.search(r"(\d+\.?\d*)\s*/\s*10", text)
        if match:
            return float(match.group(1))
        # Try single digit
        for ch in text:
            if ch.isdigit():
                return float(ch)
        return 4.0
