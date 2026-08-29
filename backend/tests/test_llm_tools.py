import json

import httpx
import pytest

from app.llm.base import LLMError, LLMMessage
from app.llm.openai_compatible import OpenAICompatibleProvider


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]


def _provider(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="gpt-test",
        client=client,
    )


def _body(request):
    return json.loads(request.content.decode("utf-8"))


def _sse(*events):
    lines = [f"data: {json.dumps(event)}\n\n" for event in events]
    return "".join(lines) + "data: [DONE]\n\n"


def test_complete_with_tools_returns_content_without_tool_calls():
    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "A normal answer."}}]},
        )

    response = _provider(handler).complete(
        [LLMMessage(role="user", content="hi")], tools=TOOLS
    )

    assert response.content == "A normal answer."
    assert response.tool_calls is None


def test_complete_with_tools_parses_one_tool_call():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "model": "gpt-tool",
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"city":"Shanghai"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
            },
        )

    response = _provider(handler).complete(
        [LLMMessage(role="user", content="hi")], tools=TOOLS
    )

    assert response.content is None
    assert [(call.id, call.name, call.arguments) for call in response.tool_calls] == [
        ("call_1", "get_weather", '{"city":"Shanghai"}')
    ]
    assert response.model == "gpt-tool"


def test_complete_with_tools_parses_multiple_tool_calls_in_order():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "first", "arguments": "{}"},
                                },
                                {
                                    "id": "call_2",
                                    "type": "function",
                                    "function": {"name": "second", "arguments": '{"n":2}'},
                                },
                            ],
                        }
                    }
                ]
            },
        )

    response = _provider(handler).complete(
        [LLMMessage(role="user", content="hi")], tools=TOOLS
    )

    assert [(call.id, call.name, call.arguments) for call in response.tool_calls] == [
        ("call_1", "first", "{}"),
        ("call_2", "second", '{"n":2}'),
    ]


def test_stream_with_tools_joins_fragmented_arguments():
    sse = _sse(
        {
            "model": "gpt-tool",
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "get_weather", "arguments": '{"city":"'},
                            }
                        ]
                    }
                }
            ],
        },
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "Shanghai\""}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "}"}}]}}]},
    )

    def handler(request):
        return httpx.Response(200, content=sse.encode("utf-8"))

    chunks = list(
        _provider(handler).stream([LLMMessage(role="user", content="hi")], tools=TOOLS)
    )

    assert len(chunks) == 1
    assert chunks[0].model == "gpt-tool"
    assert [(call.id, call.name, call.arguments) for call in chunks[0].tool_calls] == [
        ("call_1", "get_weather", '{"city":"Shanghai"}')
    ]


def test_stream_with_tools_accumulates_interleaved_calls_by_index():
    sse = _sse(
        {
            "model": "gpt-tool",
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": "call_2",
                                "type": "function",
                                "function": {"name": "second", "arguments": '{"b":'},
                            },
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "first", "arguments": '{"a":'},
                            },
                        ]
                    }
                }
            ],
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"arguments": "1}"}},
                            {"index": 1, "function": {"arguments": "2}"}},
                        ]
                    }
                }
            ]
        },
    )

    def handler(request):
        return httpx.Response(200, content=sse.encode("utf-8"))

    chunks = list(
        _provider(handler).stream([LLMMessage(role="user", content="hi")], tools=TOOLS)
    )

    assert [(call.id, call.name, call.arguments) for call in chunks[-1].tool_calls] == [
        ("call_1", "first", '{"a":1}'),
        ("call_2", "second", '{"b":2}'),
    ]


@pytest.mark.parametrize(
    ("response_json", "sse"),
    [
        (
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "bad", "arguments": {}},
                                }
                            ],
                        }
                    }
                ]
            },
            None,
        ),
        (
            None,
            _sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": {}},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ),
        ),
    ],
)
def test_tools_malformed_data_raises_llm_error(response_json, sse):
    def handler(request):
        if sse is not None:
            return httpx.Response(200, content=sse.encode("utf-8"))
        return httpx.Response(200, json=response_json)

    provider = _provider(handler)
    with pytest.raises(LLMError):
        if sse is None:
            provider.complete([LLMMessage(role="user", content="hi")], tools=TOOLS)
        else:
            list(provider.stream([LLMMessage(role="user", content="hi")], tools=TOOLS))


def test_tools_are_sent_in_upstream_payload():
    captured = {}

    def handler(request):
        captured["body"] = _body(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _provider(handler).complete([LLMMessage(role="user", content="hi")], tools=TOOLS)

    assert captured["body"]["tools"] == TOOLS


def test_without_tools_keeps_payload_and_empty_content_behavior():
    captured = []
    sse = _sse({"choices": [{"delta": {"content": "streamed"}}]})

    def handler(request):
        captured.append(_body(request))
        if captured[-1]["stream"]:
            return httpx.Response(200, content=sse.encode("utf-8"))
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    provider = _provider(handler)
    with pytest.raises(LLMError, match="上游返回空内容"):
        provider.complete([LLMMessage(role="user", content="hi")])

    chunks = list(provider.stream([LLMMessage(role="user", content="hi")]))

    assert [chunk.content for chunk in chunks] == ["streamed"]
    assert all("tools" not in payload for payload in captured)


def test_stream_without_tools_skips_empty_choices_chunk():
    sse = _sse(
        {"choices": []},
        {"choices": [{"delta": {"content": "streamed"}}]},
    )

    def handler(request):
        return httpx.Response(200, content=sse.encode("utf-8"))

    chunks = list(_provider(handler).stream([LLMMessage(role="user", content="hi")]))

    assert [chunk.content for chunk in chunks] == ["streamed"]
