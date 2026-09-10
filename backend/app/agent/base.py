from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session


class ToolError(Exception):
    """Raised when a tool cannot be registered or used safely."""


class ToolResult(BaseModel):
    """A safe, serializable result returned by a tool."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    content: str
    data: dict | None = None
    error_code: str | None = None


@dataclass
class ToolContext:
    """Server-injected values that are never part of a tool input schema."""

    user_id: int
    session: Session
    project_id: int | None = None


class Tool(ABC):
    name: str
    description: str
    input_schema: type[BaseModel]

    @abstractmethod
    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        """Execute this tool with validated arguments and server context."""
        raise NotImplementedError
