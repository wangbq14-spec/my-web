"""LLM Provider 手工 smoke test。

用法（在 backend/ 目录下，已配置 .env 的 LLM_* 变量）：
    uv run python scripts/llm_smoke_test.py

注意：
- 本脚本会发起一次真实 LLM 请求，消耗少量真实 API Token。
- 不加入 pytest 默认测试路径（pytest testpaths 仅为 tests/）。
- 绝不打印 API Key 或 Authorization header。
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.llm.base import LLMError, LLMMessage  # noqa: E402
from app.llm.factory import get_llm_provider  # noqa: E402


def main() -> None:
    try:
        provider = get_llm_provider()
    except LLMError as exc:
        print(f"[FAIL] provider 初始化失败: {type(exc).__name__}: {exc}")
        return

    try:
        response = provider.complete(
            [LLMMessage(role="user", content="只回复 OK")],
        )
    except LLMError as exc:
        print(f"[FAIL] 调用失败: {type(exc).__name__}: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        # 兜底：只打印异常类型，避免打印任何可能含敏感信息的消息
        print(f"[FAIL] 未知错误: {type(exc).__name__}")
        return

    print("[OK] 调用成功")
    print(f"model:   {response.model}")
    print(f"content: {response.content}")


if __name__ == "__main__":
    main()
