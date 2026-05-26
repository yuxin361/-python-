"""
报告拆分导出模块 - 将完整拆解报告分割为 8 个独立 Markdown 文件。

支持两种拆分策略：
1. LLM 拆分：由 AI 识别模块边界并分割（优先）
2. 正则回退：基于标题模式的本地拆分（备选）
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

from src.config import OUTPUT_DIR, HISTORY_DIR, OUTPUT_FILES, OUTPUT_MODULE_TITLES
from src.llm import LLMClient
from src.models import NovelUnpackConfig, HistoryRecord
from src.prompt_manager import PromptManager

logger = logging.getLogger("novel_unpack.splitter")


class ReportSplitter:
    """拆解报告拆分与保存器。"""

    def __init__(self, llm_client: LLMClient, prompt_mgr: PromptManager) -> None:
        self.llm = llm_client
        self.prompts = prompt_mgr

    def split_and_save(
        self,
        report_content: str,
        config: NovelUnpackConfig,
    ) -> list[str]:
        """将报告拆分为 8 个文件并保存。

        Args:
            report_content: 完整拆解报告
            config: 拆书配置

        Returns:
            已保存的文件名列表
        """
        book_dir = config.output_dir / config.novel_title
        book_dir.mkdir(parents=True, exist_ok=True)

        file_blocks = self._llm_split(report_content)

        if not file_blocks:
            logger.warning("LLM 拆分失败，使用备选拆分策略")
            file_blocks = self._fallback_split(report_content, config)

        saved_files: list[str] = []
        for filename, content in file_blocks:
            filepath = book_dir / filename
            filepath.write_text(content.strip(), encoding="utf-8")
            saved_files.append(filename)
            logger.info("已保存: %s (%d bytes)", filename, len(content.strip()))

        self._save_history(config, saved_files, str(book_dir))

        return saved_files

    def _llm_split(self, report_content: str) -> list[tuple[str, str]]:
        """使用 LLM 进行智能拆分。"""
        split_prompt = self.prompts.format(
            "07_split_export.txt",
            report_content=report_content,
        )

        result = self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是 Markdown 文档拆分专家。严格按照 ===FILE:...=== 格式拆分报告。",
                },
                {"role": "user", "content": split_prompt},
            ],
            temperature=0.1,
            max_tokens=16384,
        )

        file_blocks = re.findall(
            r"===FILE:(.+?)===\n(.*?)===END===",
            result,
            re.DOTALL,
        )

        return [(name.strip(), content.strip()) for name, content in file_blocks]

    def _fallback_split(
        self,
        report_content: str,
        config: NovelUnpackConfig,
    ) -> list[tuple[str, str]]:
        """基于正则表达式的备选拆分策略。

        按 ## 二级标题分割报告，匹配到对应模块标题则提取内容。
        """
        sections = re.split(r"\n(?=## )", report_content)
        book_title = f"《{config.novel_title}》全书深度拆解报告"

        file_blocks: list[tuple[str, str]] = []

        for filename, module_title in zip(OUTPUT_FILES, OUTPUT_MODULE_TITLES):
            content_parts: list[str] = [f"# {book_title}\n"]
            found = False

            for sec in sections:
                if sec.strip().startswith(f"## {module_title}") or module_title in sec[:60]:
                    content_parts.append(sec.strip())
                    found = True
                    break

            if not found:
                content_parts.append(f"## {module_title}\n（内容暂缺 - 请重新生成完整报告）")

            file_blocks.append((filename, "\n\n".join(content_parts)))

        return file_blocks

    @staticmethod
    def _save_history(
        config: NovelUnpackConfig,
        saved_files: list[str],
        output_dir: str,
    ) -> None:
        """保存拆解历史记录。"""
        record = HistoryRecord.from_config(config, saved_files, output_dir)
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)

        history_file = HISTORY_DIR / f"{config.novel_title}_{int(time.time())}.json"
        history_file.write_text(record.to_json(), encoding="utf-8")
        logger.info("历史记录已保存: %s", history_file.name)