"""
工作流引擎模块 - 核心拆书工作流编排。

按 7 个步骤顺序执行：
1. 搜索 → 2. 用户选择 → 3. 提取书名 → 4. 生成报告
→ 5. 质量校验 → 6. 拆分保存 → 7. 完成

支持回调机制，可与 GUI 或 CLI 界面解耦。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from src.config import (
    ensure_directories,
    DEPTH_CONFIG,
    OUTPUT_DIR,
)
from src.models import (
    NovelUnpackConfig,
    SearchResult,
    WorkflowState,
)
from src.llm import LLMClient
from src.prompt_manager import PromptManager
from src.search import SearchService
from src.checker import QualityChecker
from src.splitter import ReportSplitter

logger = logging.getLogger("novel_unpack.workflow")


@dataclass
class WorkflowCallbacks:
    """工作流回调函数集合，用于与界面层解耦。"""
    on_log: Callable[[str, str], None] = lambda msg, tag: None
    on_status: Callable[[str], None] = lambda status: None
    on_search_results: Callable[[list[SearchResult]], Optional[int]] = lambda r: None
    on_finished: Callable[[NovelUnpackConfig, list[str], Path], None] = lambda c, f, p: None
    on_error: Callable[[Exception], None] = lambda e: None


class WorkflowEngine:
    """拆书工作流引擎。

    按 7 步骤串联执行整个拆书流程。
    通过 WorkflowCallbacks 与界面层交互。
    """

    def __init__(
        self,
        config: NovelUnpackConfig,
        llm_client: LLMClient,
        prompt_mgr: PromptManager,
        search_svc: SearchService,
        callbacks: Optional[WorkflowCallbacks] = None,
    ) -> None:
        self.config = config
        self.llm = llm_client
        self.prompts = prompt_mgr
        self.search = search_svc
        self.callbacks = callbacks or WorkflowCallbacks()

        self.state = WorkflowState()
        self.checker = QualityChecker(llm_client, prompt_mgr)
        self.splitter = ReportSplitter(llm_client, prompt_mgr)

        self._running = False

    # ===================== 公共方法 =====================

    def run(self) -> None:
        """执行完整的拆书工作流。"""
        self._running = True
        self.state.start_time = time.time()
        ensure_directories()

        try:
            self._log("=" * 50, "header")
            self._log(f"📖 开始拆解：《{self.config.novel_name}》", "header")
            self._log(f"深度：{self.config.depth} ({DEPTH_CONFIG[self.config.depth]['label']})", "header")
            self._log(f"图表数量：≥{self.config.chart_count}", "header")
            self._log("=" * 50, "header")

            self._step_search()
            if not self._running:
                return

            self._step_user_select()
            if not self._running:
                return

            self._step_extract_title()
            if not self._running:
                return

            self._step_generate_report()
            if not self._running:
                return

            self._step_quality_check()
            if not self._running:
                return

            self._step_split_save()
            if not self._running:
                return

            self._step_finish()

        except Exception as exc:
            self._log(f"❌ 流程异常终止：{exc}", "error")
            logger.exception("Workflow error")
            self.callbacks.on_error(exc)
            raise

        finally:
            self._running = False

    def stop(self) -> None:
        """停止当前正在运行的工作流。"""
        self._running = False
        self._log("⏹ 工作流已手动停止", "warn")

    @property
    def is_running(self) -> bool:
        return self._running

    # ===================== 步骤 1: 搜索 =====================

    def _step_search(self) -> None:
        self._log("🔍 [步骤 1/7] 构造搜索关键词...", "step")
        self._update_status("搜索中...")

        query_prompt = self.prompts.format(
            "01_search_query.txt",
            novel_name=self.config.novel_name,
        )
        query_result = self.llm.chat(
            messages=[
                {"role": "system", "content": "你是一个搜索关键词优化专家。"},
                {"role": "user", "content": query_prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )

        search_query = query_result.strip().strip('"').strip("'")
        self._log(f"  搜索词：{search_query}", "info")

        results = self.search.search(search_query, count=5)
        self.state.search_results = results

        search_raw_lines = []
        for r in results:
            line = f"{r.index}. 《{r.title}》 - {r.author}"
            if r.description:
                line += f" {r.description}"
            search_raw_lines.append(line)

        self.state.search_raw = "\n".join(search_raw_lines)

        self._log(f"  找到 {len(results)} 条结果", "info")
        for r in results:
            self._log(f"  {r.format_full()}", "info")

    # ===================== 步骤 2: 用户选择 =====================

    def _step_user_select(self) -> None:
        self._log("\n✋ [步骤 2/7] 用户选择候选条目", "step")
        self._update_status("请选择候选条目")

        results = self.state.search_results
        if not results:
            self.state.selected_index = 1
            self._log("  无搜索结果，默认选择第1项", "warn")
            return

        selection_guide = self.prompts.format(
            "02_selection_guide.txt",
            novel_name=self.config.novel_name,
        )
        self.state.selection_guide = selection_guide

        selected = self.callbacks.on_search_results(results)
        if selected is not None:
            self.state.selected_index = selected
            self._log(f"  用户选择序号：{selected}", "success")
        else:
            self.state.selected_index = 1
            self._log("  用户未选择，默认第1项", "warn")

    # ===================== 步骤 3: 提取书名 =====================

    def _step_extract_title(self) -> None:
        self._log("\n📝 [步骤 3/7] 提取标准书名与作者...", "step")
        self._update_status("提取书名信息...")

        prompt = self.prompts.format(
            "03_extract_title.txt",
            search_result=self.state.search_raw,
            selected_index=self.state.selected_index,
        )
        result = self.llm.chat(
            messages=[
                {"role": "system", "content": "从搜索结果中精确提取书名和作者。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=200,
        )

        title_match = re.search(r"书名[：:]\s*《(.+?)》", result)
        author_match = re.search(r"作者[：:]\s*(.+)", result)

        self.config.novel_title = title_match.group(1) if title_match else self.config.novel_name
        self.config.author = author_match.group(1).strip() if author_match else "未知"

        self._log(f"  书名：《{self.config.novel_title}》", "success")
        self._log(f"  作者：{self.config.author}", "success")

    # ===================== 步骤 4: 生成报告 =====================

    def _step_generate_report(self) -> None:
        self._log("\n✍️  [步骤 4/7] 生成深度拆解报告（可能需要1-3分钟）...", "step")
        self._update_status("AI 正在生成拆解报告中...")

        system_prompt = self.prompts.load("04_deep_unpack_system.txt")
        user_prompt = self.prompts.format(
            "05_deep_unpack_user.txt",
            book_name=self.config.novel_title,
            author=self.config.author,
            depth=self.config.depth,
            chart_count=self.config.chart_count,
        )

        max_tokens = DEPTH_CONFIG[self.config.depth]["max_tokens"]

        report = self.llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=max_tokens,
        )

        self.state.report_content = report
        char_count = len(report)
        mermaid_count = report.count("```mermaid")

        self._log(f"  ✅ 报告生成完成！", "success")
        self._log(f"  总字数：约{char_count}字", "info")
        self._log(f"  包含 {mermaid_count} 个 Mermaid 图表", "info")

    # ===================== 步骤 5: 质量校验 =====================

    def _step_quality_check(self) -> None:
        self._log("\n🔎 [步骤 5/7] 质量校验...", "step")
        self._update_status("质量校验中...")

        check_result = self.checker.check(
            self.state.report_content,
            min_chart_count=self.config.chart_count,
        )

        self.state.quality_check_result = check_result.raw_feedback
        self.state.quality_passed = check_result.passed

        if check_result.passed:
            self._log("  ✅ 质量校验通过！", "success")
            return

        self._log("  ⚠️ 校验发现问题：", "warn")
        if check_result.missing_modules:
            self._log(f"    缺失模块：{check_result.missing_modules}", "warn")
        if check_result.missing_charts:
            self._log(f"    缺失图表：{check_result.missing_charts}", "warn")
        if check_result.insufficient_content:
            self._log(f"    内容不足：{check_result.insufficient_content[:200]}", "warn")

        self._update_status("正在进行补充修复...")
        self._log("  🔧 正在进行补充修复...", "step")

        fixed = self.checker.auto_fix(
            self.state.report_content,
            check_result,
        )

        self.state.report_content = fixed
        self._log("  ✅ 补充修复完成", "success")

    # ===================== 步骤 6: 拆分保存 =====================

    def _step_split_save(self) -> None:
        self._log("\n📁 [步骤 6/7] 拆分并保存为独立文件...", "step")
        self._update_status("拆分保存中...")

        saved_files = self.splitter.split_and_save(
            self.state.report_content,
            self.config,
        )

        self.state.saved_files = saved_files
        self.state.book_output_dir = self.config.output_dir / self.config.novel_title

        self._log(f"  共保存 {len(saved_files)} 个文件", "success")
        for fname in saved_files:
            self._log(f"  ✅ {fname}", "success")

    # ===================== 步骤 7: 完成 =====================

    def _step_finish(self) -> None:
        book_dir = self.state.book_output_dir or (
            self.config.output_dir / self.config.novel_title
        )
        saved = self.state.saved_files

        elapsed = self.state.elapsed_seconds()
        self._log("\n" + "=" * 50, "header")
        self._log("🎉 [步骤 7/7] 拆解完成！", "header")
        self._log("=" * 50, "header")
        self._log(f"📂 输出目录：{book_dir}", "success")
        self._log(f"📄 共生成 {len(saved)} 个文件", "success")
        for f in saved:
            self._log(f"  ├─ {f}", "info")
        self._log(f"  └─ 报告总字数：约{len(self.state.report_content)}字", "info")
        self._log(f"⏱️  总耗时：{elapsed:.1f} 秒", "info")
        self._log("\n💡 提示：可在 Typora / VS Code / GitHub 中查看渲染效果", "success")

        self._update_status("拆解完成 ✅")

        self.callbacks.on_finished(self.config, saved, book_dir)

    # ===================== 辅助方法 =====================

    def _log(self, message: str, tag: str = "info") -> None:
        logger.info("[%s] %s", tag, message)
        self.callbacks.on_log(message, tag)

    def _update_status(self, text: str) -> None:
        self.callbacks.on_status(text)