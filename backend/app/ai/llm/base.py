from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class LLMError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class LLMNotConfigured(LLMError):
    pass


@dataclass
class LLMRequest:
    system: str  # stable instructions (cacheable)
    user: str  # task-specific content incl. delimited untrusted data
    model: str
    max_tokens: int = 1800
    temperature: float | None = None
    json_mode: bool = True
    effort: str | None = None  # anthropic only
    timeout: float = 90.0


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    stop_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    name: str = ""

    @abstractmethod
    def complete(self, req: LLMRequest) -> LLMResponse: ...
