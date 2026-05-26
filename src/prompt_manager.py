"""
提示词管理器模块 - 加载、格式化和管理所有提示词文件。

提示词文件位于 prompts/ 目录，均为纯文本 .txt 文件。
支持 {placeholder} 模板变量替换。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from src.config import PROMPTS_DIR

logger = logging.getLogger("novel_unpack.prompts")


class PromptManager:
    """提示词管理器。

    负责加载 prompts/ 目录下的 .txt 提示词文件，
    并提供模板变量替换功能。
    """

    def __init__(self, prompts_dir: Optional[Path] = None) -> None:
        self.prompts_dir = prompts_dir or PROMPTS_DIR
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"提示词目录不存在: {self.prompts_dir}")

        self._cache: dict[str, str] = {}

    def list_prompts(self) -> list[str]:
        """列出所有可用的提示词文件名。"""
        return sorted(
            p.name for p in self.prompts_dir.iterdir()
            if p.suffix == ".txt" and not p.name.startswith(".")
        )

    def load(self, filename: str) -> str:
        """加载提示词文件内容。

        Args:
            filename: 提示词文件名（如 '01_search_query.txt'）

        Returns:
            提示词文件内容字符串

        Raises:
            FileNotFoundError: 文件不存在
        """
        if filename in self._cache:
            return self._cache[filename]

        path = self.prompts_dir / filename
        if not path.exists():
            available = self.list_prompts()
            raise FileNotFoundError(
                f"提示词文件不存在: {filename}\n"
                f"可用文件: {', '.join(available)}"
            )

        content = path.read_text("utf-8")
        self._cache[filename] = content
        return content

    def format(self, filename: str, **kwargs: Any) -> str:
        """加载提示词模板并填充变量。

        Args:
            filename: 提示词文件名
            **kwargs: 模板变量键值对

        Returns:
            填充后的完整提示词

        Example:
            >>> pm = PromptManager()
            >>> pm.format("05_deep_unpack_user.txt",
            ...           book_name="三体", author="刘慈欣",
            ...           depth=2, chart_count=4)
        """
        template = self.load(filename)
        return template.format(**kwargs)

    def clear_cache(self) -> None:
        """清空提示词缓存。"""
        self._cache.clear()
        logger.debug("提示词缓存已清空")

    def get_prompt_info(self, filename: str) -> dict[str, Any]:
        """获取提示词文件的元信息。"""
        content = self.load(filename)
        lines = content.strip().split("\n")
        first_line = lines[0] if lines else ""
        return {
            "filename": filename,
            "size": len(content),
            "lines": len(lines),
            "first_line": first_line[:100],
            "has_placeholders": "{" in content,
        }