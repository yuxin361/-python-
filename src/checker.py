"""
质量校验模块 - 校验拆解报告是否满足标准。

使用 LLM 检查报告的模块完整性、图表数量、内容充实度。
"""

from __future__ import annotations

import logging
from typing import Optional

from src.models import QualityCheckResult
from src.llm import LLMClient
from src.prompt_manager import PromptManager

logger = logging.getLogger("novel_unpack.checker")


class QualityChecker:
    """拆解报告质量校验器。"""

    def __init__(self, llm_client: LLMClient, prompt_mgr: PromptManager) -> None:
        self.llm = llm_client
        self.prompts = prompt_mgr

    def check(
        self,
        report_content: str,
        min_chart_count: int = 4,
    ) -> QualityCheckResult:
        """对报告进行质量校验。

        Args:
            report_content: 完整拆解报告内容
            min_chart_count: 最低要求的 Mermaid 图表数量

        Returns:
            校验结果
        """
        quality_prompt = self.prompts.format(
            "06_quality_check_system.txt",
            report_content=report_content,
            chart_count=min_chart_count,
        )

        response = self.llm.chat(
            messages=[
                {"role": "system", "content": "你是一个严格的质量审核员。"},
                {"role": "user", "content": quality_prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
        )

        result = QualityCheckResult.from_llm_response(response)

        if result.passed:
            logger.info("质量校验: ✅ 通过")
        else:
            logger.warning(
                "质量校验: ⚠️ 发现问题 - 缺失模块=%s, 缺失图表=%s, 内容问题=%s",
                result.missing_modules,
                result.missing_charts,
                result.insufficient_content[:100] if result.insufficient_content else "无",
            )

        return result

    def auto_fix(
        self,
        report_content: str,
        check_result: QualityCheckResult,
    ) -> str:
        """根据校验结果自动补全报告。

        Args:
            report_content: 原报告内容
            check_result: 校验结果

        Returns:
            补全后的报告内容
        """
        fix_prompt = (
            f"以下是一份小说拆解报告，经质量检查发现以下问题：\n\n"
            f"{check_result.raw_feedback}\n\n"
            f"请根据以上缺失项补充缺失的内容，输出完整修复后的报告"
            f"（包含所有原内容和新补充的内容）。\n"
            f"确保每个模块内容详尽，所有Mermaid代码块完整正确。\n\n"
            f"原报告：\n{report_content}"
        )

        system_prompt = self.prompts.load("04_deep_unpack_system.txt")

        logger.info("正在进行自动补全修复...")
        fixed = self.llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": fix_prompt},
            ],
            temperature=0.5,
            max_tokens=20000,
        )

        return fixed

    @staticmethod
    def quick_check(report_content: str) -> dict[str, bool | int]:
        """快速本地检查（无需 LLM 调用）。

        检查报告的基本结构完整性。

        Returns:
            检查结果字典
        """
        checks: dict[str, bool | int] = {}

        mermaid_count = report_content.count("```mermaid")
        checks["mermaid_count"] = mermaid_count
        checks["has_mermaid"] = mermaid_count >= 1

        char_count = len(report_content)
        checks["char_count"] = char_count
        checks["sufficient_length"] = char_count > 6000

        module_titles = [
            "小说概览",
            "人物图鉴与关系网",
            "情节结构与伏笔",
            "世界观设定集",
            "故事线与叙事节奏",
            "写作技法与金句",
            "情感弧线与主题",
            "综合评价",
        ]

        found_modules: list[str] = []
        for title in module_titles:
            if title in report_content:
                found_modules.append(title)

        checks["found_modules"] = found_modules
        checks["all_modules_present"] = len(found_modules) == len(module_titles)

        checks["has_placeholder"] = "略" in report_content or "占位符" in report_content

        return checks