from app.agent.base import Tool, ToolError
from app.agent.tools.calculator import CalculatorTool
from app.agent.tools.knowledge_search import KnowledgeSearchTool


class ToolRegistry:
    """An in-memory registry independent of concrete business tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ToolError("Tool name must not be empty")
        if tool.name in self._tools:
            raise ToolError("Tool name is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def to_llm_schema(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema.model_json_schema(),
                },
            }
            for tool in self._tools.values()
        ]


def build_agent_registry() -> ToolRegistry:
    """Build the built-in read-only tool registry for an agent run."""

    registry = ToolRegistry()
    registry.register(KnowledgeSearchTool())
    registry.register(CalculatorTool())
    return registry
