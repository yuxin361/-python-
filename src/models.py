"""
数据模型模块 - 定义所有核心数据结构。
"""

from __future__ import annotations

import time
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from src.config import OUTPUT_DIR


# ===================== 核心配置模型 =====================

@dataclass
class NovelUnpackConfig:
    """拆书任务配置。"""
    novel_name: str
    depth: int = 2
    chart_count: int = 4
    novel_title: str = ""
    author: str = ""
    api_base: str = ""
    api_key: str = ""
    llm_model: str = "gpt-4o"
    output_dir: Path = OUTPUT_DIR


# ===================== 搜索结果模型 =====================

@dataclass
class SearchResult:
    """搜索结果条目。"""
    index: int
    title: str
    author: str = ""
    year: str = ""
    description: str = ""

    def format_short(self) -> str:
        parts = [f"[{self.index}] 《{self.title}》"]
        if self.author:
            parts[-1] += f" - {self.author}"
        if self.year:
            parts[-1] += f" ({self.year})"
        return parts[-1]

    def format_full(self) -> str:
        text = self.format_short()
        if self.description:
            text += f"\n    {self.description}"
        return text


# ===================== 工作流状态模型 =====================

@dataclass
class WorkflowState:
    """工作流运行时状态，在各步骤间传递数据。"""
    search_results: list[SearchResult] = field(default_factory=list)
    search_raw: str = ""
    selected_index: int = 1
    selection_guide: str = ""
    report_content: str = ""
    quality_check_result: str = ""
    quality_passed: bool = False
    saved_files: list[str] = field(default_factory=list)
    book_output_dir: Optional[Path] = None
    start_time: float = 0.0

    def elapsed_seconds(self) -> float:
        if self.start_time == 0:
            return 0.0
        return time.time() - self.start_time

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ===================== 质量校验结果模型 =====================

@dataclass
class QualityCheckResult:
    """质量校验结果。"""
    passed: bool = False
    missing_modules: list[str] = field(default_factory=list)
    missing_charts: list[str] = field(default_factory=list)
    insufficient_content: str = ""
    raw_feedback: str = ""

    @classmethod
    def from_llm_response(cls, response: str) -> QualityCheckResult:
        """解析 LLM 的校验响应。"""
        result = cls(raw_feedback=response.strip())

        stripped = response.strip()
        if stripped == "PASS" or "PASS" in stripped[:10]:
            result.passed = True
            return result

        modules_section = ""
        charts_section = ""
        content_section = ""

        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("MISSING_MODULES:"):
                modules_section = line.replace("MISSING_MODULES:", "").strip()
            elif line.startswith("MISSING_CHARTS:"):
                charts_section = line.replace("MISSING_CHARTS:", "").strip()
            elif line.startswith("INSUFFICIENT_CONTENT:"):
                content_section = line.replace("INSUFFICIENT_CONTENT:", "").strip()

        if modules_section:
            result.missing_modules = [
                m.strip().strip("{}").strip("[]")
                for m in modules_section.split(",")
            ]
        if charts_section:
            result.missing_charts = [
                c.strip().strip("{}").strip("[]")
                for c in charts_section.split(",")
            ]
        if content_section:
            result.insufficient_content = content_section

        return result


# ===================== 历史记录模型 =====================

@dataclass
class HistoryRecord:
    """单次拆解的历史记录。"""
    book_title: str
    author: str
    depth: int
    saved_files: list[str]
    timestamp: str = ""
    output_dir: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_config(
        cls,
        config: NovelUnpackConfig,
        saved_files: list[str],
        output_dir: str,
    ) -> HistoryRecord:
        return cls(
            book_title=config.novel_title,
            author=config.author,
            depth=config.depth,
            saved_files=saved_files,
            output_dir=output_dir,
        )