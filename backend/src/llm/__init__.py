"""Слой доступа к модели."""

from src.llm.cache import ResponseCache, cache_key
from src.llm.contracts import (
    Claim,
    ClaimVerdict,
    ClassifyResult,
    DedupPairResult,
    Entities,
    ScoreResultRaw,
    SummarizeResult,
    VerifyClaimsResult,
)
from src.llm.provider import (
    FallbackProvider,
    LLMError,
    LLMProvider,
    OpenAICompatibleProvider,
    build_provider,
)

__all__ = [
    "Claim",
    "ClaimVerdict",
    "ClassifyResult",
    "DedupPairResult",
    "Entities",
    "FallbackProvider",
    "LLMError",
    "LLMProvider",
    "OpenAICompatibleProvider",
    "ResponseCache",
    "ScoreResultRaw",
    "SummarizeResult",
    "VerifyClaimsResult",
    "build_provider",
    "cache_key",
]
