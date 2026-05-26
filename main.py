"""
novel_unpack_final - 统一入口

支持两种运行模式：
  python main.py              → 启动 GUI 图形界面（默认）
  python main.py --cli "三体" → 启动 CLI 命令行模式
"""

from __future__ import annotations

import sys


def run_gui() -> None:
    """启动 GUI 模式。"""
    from src.simple_gui import SimpleNovelUnpackGUI
    app = SimpleNovelUnpackGUI()
    app.run()


def run_cli() -> None:
    """启动 CLI 模式。"""
    from src.cli import main as cli_main
    cli_main()


def main() -> None:
    """主入口 - 根据参数决定运行模式。"""
    if len(sys.argv) > 1 and sys.argv[1] in ("--cli", "-c", "--text"):
        sys.argv.pop(1)
        run_cli()
    else:
        run_gui()


if __name__ == "__main__":
    main()