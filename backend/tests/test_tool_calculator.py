import inspect

import pytest
from pydantic import ValidationError

from app.agent.tools.calculator import CalculatorInput, CalculatorTool


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2", "3"),
        ("8 - 3", "5"),
        ("6 * 7", "42"),
        ("8 / 2", "4.0"),
        ("(2 + 3) * 4", "20"),
    ],
)
def test_calculator_handles_basic_arithmetic_and_parentheses(expression, expected):
    result = CalculatorTool().execute(CalculatorInput(expression=expression), None)

    assert result.success is True
    assert result.content == expected
    assert result.data is None


@pytest.mark.parametrize(
    "expression",
    [
        "1 +",
        "__import__('os')",
        "open('private')",
        "x",
        "[1, 2]",
        '"abc"',
        "(1).real",
        "import os",
        "(lambda: 1)()",
    ],
)
def test_calculator_rejects_invalid_or_code_like_expressions(expression):
    result = CalculatorTool().execute(CalculatorInput(expression=expression), None)

    assert result.success is False
    assert result.error_code == "invalid_expression"
    assert result.content == "非法表达式"


@pytest.mark.parametrize("expression", ["1 / 0", "1 % 0", "1 // 0"])
def test_calculator_reports_division_by_zero(expression):
    result = CalculatorTool().execute(CalculatorInput(expression=expression), None)

    assert result.success is False
    assert result.error_code == "division_by_zero"


@pytest.mark.parametrize("expression", ["2 ** 101", "2 ** -101", "1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1"])
def test_calculator_enforces_complexity_limits(expression):
    result = CalculatorTool().execute(CalculatorInput(expression=expression), None)

    assert result.success is False
    assert result.error_code == "complexity_limit"


def test_calculator_input_enforces_length_limit():
    with pytest.raises(ValidationError):
        CalculatorInput(expression="1" * 201)


def test_calculator_does_not_use_dynamic_code_execution():
    source = inspect.getsource(CalculatorTool)

    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
