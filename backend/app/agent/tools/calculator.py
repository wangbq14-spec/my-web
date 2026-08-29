import ast
import math

from pydantic import BaseModel, ConfigDict, Field

from app.agent.base import Tool, ToolResult, ToolContext


class CalculatorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str = Field(min_length=1, max_length=200)


class _CalculatorFailure(Exception):
    def __init__(self, error_code: str, content: str) -> None:
        self.error_code = error_code
        self.content = content
        super().__init__(content)


class CalculatorTool(Tool):
    name = "calculator"
    description = "计算整数或小数表达式，支持 +、-、*、/、%、//、括号和幂运算。"
    input_schema = CalculatorInput
    _MAX_AST_NODES = 64

    def execute(self, args: CalculatorInput, context: ToolContext) -> ToolResult:
        del context
        try:
            expression = ast.parse(args.expression, mode="eval")
            if not isinstance(expression, ast.Expression):
                raise _CalculatorFailure("invalid_expression", "非法表达式")
            if sum(1 for _ in ast.walk(expression)) > self._MAX_AST_NODES:
                raise _CalculatorFailure("complexity_limit", "表达式复杂度超限")

            result = self._calculate(expression.body)
            self._require_finite(result)
        except SyntaxError:
            return ToolResult(
                success=False, error_code="invalid_expression", content="非法表达式"
            )
        except _CalculatorFailure as error:
            return ToolResult(
                success=False, error_code=error.error_code, content=error.content
            )

        return ToolResult(success=True, content=str(result), data=None)

    def _calculate(self, node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise _CalculatorFailure("invalid_expression", "非法表达式")
            self._require_finite(node.value)
            return node.value

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self._calculate(node.operand)
            result = value if isinstance(node.op, ast.UAdd) else -value
            self._require_finite(result)
            return result

        if not isinstance(node, ast.BinOp):
            raise _CalculatorFailure("invalid_expression", "非法表达式")
        if not isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv)
        ):
            raise _CalculatorFailure("invalid_expression", "非法表达式")

        left = self._calculate(node.left)
        right = self._calculate(node.right)
        if isinstance(node.op, (ast.Div, ast.Mod, ast.FloorDiv)) and right == 0:
            raise _CalculatorFailure("division_by_zero", "除数不能为零")
        if isinstance(node.op, ast.Pow) and isinstance(right, int) and abs(right) > 100:
            raise _CalculatorFailure("complexity_limit", "表达式复杂度超限")

        try:
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div):
                result = left / right
            elif isinstance(node.op, ast.Mod):
                result = left % right
            elif isinstance(node.op, ast.FloorDiv):
                result = left // right
            else:
                result = left**right
        except OverflowError as error:
            raise _CalculatorFailure("non_finite", "计算结果不是有限数") from error

        self._require_finite(result)
        return result

    @staticmethod
    def _require_finite(value: int | float) -> None:
        try:
            is_finite = math.isfinite(value)
        except OverflowError:
            is_finite = False
        if not is_finite:
            raise _CalculatorFailure("non_finite", "计算结果不是有限数")
