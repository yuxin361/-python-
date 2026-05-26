"""
CLI 命令行模式 - 无需图形界面的拆书工作流。

适合在服务器或无桌面环境的场景下使用。
可通过命令行参数指定小说名称和配置。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from src.config import (
    PROMPTS_DIR,
    ensure_directories,
    load_dotenv_if_available,
    get_api_key,
    get_api_base,
    get_llm_model,
    get_bing_api_key,
    OUTPUT_FILES,
)
from src.models import NovelUnpackConfig, SearchResult
from src.llm import LLMClient
from src.prompt_manager import PromptManager
from src.search import SearchService
from src.workflow import WorkflowEngine, WorkflowCallbacks

logger = logging.getLogger("novel_unpack.cli")


def setup_logging(verbose: bool = False) -> None:
    """配置命令行日志输出。"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="📚 终极拆书工作流 CLI - 全提示词驱动的深度拆书系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python main.py --cli \"三体\"            # 使用默认设置拆解《三体》\n"
            "  python main.py --cli \"三体\" -d 3 -c 6  # 深度3级，至少6个图表\n"
            "  python main.py --cli \"三体\" --auto     # 全自动模式（无选择确认）\n"
            "  python main.py --cli \"三体\" -v         # 显示详细日志\n"
        ),
    )
    parser.add_argument("novel_name", nargs="?", default="", help="小说名称")
    parser.add_argument("-d", "--depth", type=int, default=2, choices=[1, 2, 3],
                        help="拆解深度: 1=精要, 2=标准, 3=深入 (默认: 2)")
    parser.add_argument("-c", "--chart-count", type=int, default=4,
                        help="最低图表数量 (默认: 4)")
    parser.add_argument("--auto", action="store_true",
                        help="自动模式，不提示用户选择，直接使用第一条搜索结果")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="显示详细调试日志")
    return parser.parse_args(argv)


def run_cli(args: argparse.Namespace) -> None:
    """以 CLI 模式运行工作流。"""
    load_dotenv_if_available()
    ensure_directories()

    novel_name = args.novel_name
    if not novel_name:
        novel_name = input("📖 请输入小说名称: ").strip()
        if not novel_name:
            print("❌ 小说名称不能为空")
            return

    api_key = get_api_key()
    if not api_key:
        print(
            "❌ 未找到 API Key。请设置环境变量或创建 .env 文件。\n"
            "   支持的变量: OPENAI_API_KEY, DASHSCOPE_API_KEY, DEEPSEEK_API_KEY"
        )
        return

    api_base = get_api_base()
    model = get_llm_model()
    bing_key = get_bing_api_key()

    config = NovelUnpackConfig(
        novel_name=novel_name,
        depth=args.depth,
        chart_count=args.chart_count,
        api_base=api_base,
        api_key=api_key,
        llm_model=model,
    )

    llm_client = LLMClient(api_key, api_base, model)
    prompt_mgr = PromptManager(PROMPTS_DIR)
    search_svc = SearchService(bing_key)

    auto_select = args.auto

    callbacks = WorkflowCallbacks(
        on_log=lambda msg, tag: _cli_log(msg, tag),
        on_status=lambda status: print(f"\n📌 [{status}]", end="", flush=True),
        on_search_results=lambda results: _cli_select(results, auto_select),
        on_finished=_cli_finished,
        on_error=lambda exc: print(f"\n❌ 错误: {exc}"),
    )

    engine = WorkflowEngine(config, llm_client, prompt_mgr, search_svc, callbacks)

    try:
        engine.run()
    except KeyboardInterrupt:
        print("\n\n⏹ 用户中断")
        engine.stop()
    except Exception as exc:
        print(f"\n❌ 工作流异常: {exc}")
        sys.exit(1)


def _cli_log(message: str, tag: str = "info") -> None:
    """在 CLI 中输出日志。"""
    prefix_map = {
        "header": "\n",
        "step": "\n",
        "success": "  ✅ ",
        "error": "  ❌ ",
        "warn": "  ⚠️ ",
        "info": "  ",
    }
    prefix = prefix_map.get(tag, "  ")
    print(f"{prefix}{message}")


def _cli_select(results: list[SearchResult], auto: bool = False) -> int:
    """在 CLI 中等待用户选择搜索结果。"""
    print("\n\n📋 候选小说列表:")
    for r in results:
        print(f"  {r.format_full()}")
        if r.description:
            print(f"     {r.description}")
        print()

    if auto:
        print("  🤖 自动模式: 默认选择第1项")
        return 1

    while True:
        try:
            choice = input("请输入对应序号 (0=都不匹配): ").strip()
            if not choice:
                print("  默认选择第1项")
                return 1
            idx = int(choice)
            if 0 <= idx <= len(results):
                return idx if idx > 0 else 1
            print(f"  请输入 0-{len(results)} 之间的数字")
        except ValueError:
            print("  请输入有效数字")


def _cli_finished(config: NovelUnpackConfig, saved_files: list[str], book_dir: Path) -> None:
    """CLI 完成回调。"""
    print(f"\n{'='*50}")
    print(f"🎉 拆解完成！")
    print(f"{'='*50}")
    print(f"📂 输出目录: {book_dir}")
    print(f"📄 共生成 {len(saved_files)} 个文件:")
    for f in saved_files:
        print(f"  ├─ {f}")
    print(f"\n💡 可在 Typora / VS Code 中查看 Markdown 渲染效果")


def main() -> None:
    """CLI 入口函数。"""
    args = parse_args()
    setup_logging(args.verbose)
    run_cli(args)


if __name__ == "__main__":
    main()