"""AWS Builder integration: Amazon Bedrock summarization.

When AWS credentials + BEEBRIDGE_BEDROCK_MODEL are configured, answers
and daily summaries are rephrased by a Bedrock foundation model
(default: Amazon Nova Micro / Claude via Bedrock Converse API).
Without AWS configured, BeeBridge falls back to a deterministic
extractive summary — the pipeline, prompts, and IAM/template wiring
(infra/aws/template.yaml) are identical either way, so enabling
Bedrock is a config change, not a code change.
"""
from __future__ import annotations

import os

DEFAULT_MODEL = os.environ.get("BEEBRIDGE_BEDROCK_MODEL", "amazon.nova-micro-v1:0")


class BedrockSummarizer:
    def __init__(self, model_id: str | None = None, region: str | None = None):
        self.model_id = model_id or DEFAULT_MODEL
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self._client = None

    def available(self) -> bool:
        if os.environ.get("BEEBRIDGE_DISABLE_BEDROCK") == "1":
            return False
        try:
            import boto3  # noqa: F401
            return True
        except ImportError:
            return False

    def _bedrock(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def summarize(self, text: str, audience: str = "a senior who wants short, clear sentences") -> str:
        """Summarize with Bedrock Converse; extractive fallback offline."""
        if self.available() and os.environ.get("AWS_ACCESS_KEY_ID"):
            try:
                resp = self._bedrock().converse(
                    modelId=self.model_id,
                    messages=[{"role": "user", "content": [{"text":
                        f"Summarize for {audience}. Keep names, dates, times, doses exact.\n\n{text}"}]}],
                    inferenceConfig={"maxTokens": 300, "temperature": 0.2})
                return resp["output"]["message"]["content"][0]["text"].strip()
            except Exception:
                pass  # fall through to deterministic summary
        return extractive_summary(text)


def extractive_summary(text: str, max_sentences: int = 3) -> str:
    sentences = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    if len(sentences) <= max_sentences:
        return text.strip()
    keywords = ("appointment", "take", "call", "remember", "tomorrow", "doctor")
    ranked = sorted(sentences, key=lambda s: -sum(k in s.lower() for k in keywords))
    chosen = [s for s in sentences if s in ranked[:max_sentences]]
    out = ". ".join(chosen)
    return out if out.endswith(".") else out + "."
