from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class CompletionRequest(BaseModel):
    model: str = "mock"
    messages: list[Message] = Field(..., min_length=1)
    stream: bool = False
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
