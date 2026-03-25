"""A2A Agent Card data models."""
from pydantic import BaseModel, Field


class Skill(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str] = []
    examples: list[str] = []


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    skills: list[Skill] = []
    provider: str = ""
    documentation_url: str = ""
    authentication: dict = Field(default_factory=dict)
    healthy: bool = True
    last_checked: float = 0.0


class RegisterRequest(BaseModel):
    agent_card: AgentCard
