import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.agent.base import Tool, ToolContext, ToolError, ToolResult
from app.agent.registry import ToolRegistry


class FakeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)


class FakeTool(Tool):
    name = "fake"
    description = "A fake tool for registry tests."
    input_schema = FakeInput

    def execute(self, args: FakeInput, context: ToolContext) -> ToolResult:
        del args, context
        return ToolResult(success=True, content="ok")


def test_registry_register_get_list_and_llm_schema():
    registry = ToolRegistry()
    tool = FakeTool()

    registry.register(tool)

    assert registry.get("fake") is tool
    assert registry.list_tools() == [tool]
    assert registry.to_llm_schema() == [
        {
            "type": "function",
            "function": {
                "name": "fake",
                "description": "A fake tool for registry tests.",
                "parameters": {
                    "additionalProperties": False,
                    "properties": {"value": {"minLength": 1, "title": "Value", "type": "string"}},
                    "required": ["value"],
                    "title": "FakeInput",
                    "type": "object",
                },
            },
        }
    ]


def test_registry_rejects_empty_or_duplicate_names():
    registry = ToolRegistry()
    tool = FakeTool()
    registry.register(tool)

    with pytest.raises(ToolError):
        registry.register(FakeTool())

    empty = FakeTool()
    empty.name = ""
    with pytest.raises(ToolError):
        registry.register(empty)


def test_registry_returns_none_for_unknown_tool():
    assert ToolRegistry().get("missing") is None
