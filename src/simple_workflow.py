"""
简化版工作流引擎 - 支持生成多个报告文件和功能选择。
"""

from __future__ import annotations

import logging
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
)
from src.llm import LLMClient
from src.prompt_manager import PromptManager
from src.search import SearchService

logger = logging.getLogger("novel_unpack.simple_workflow")


@dataclass
class SimpleWorkflowCallbacks:
    """工作流回调函数集合。"""
    on_log: Callable[[str, str], None] = lambda msg, tag: None
    on_status: Callable[[str], None] = lambda status: None
    on_search_results: Callable[[list[SearchResult]], None] = lambda r: None
    on_ready_for_unpack: Callable[[str, str], None] = lambda t, a: None
    on_finished: Callable[[list[str], Path], None] = lambda f, p: None
    on_error: Callable[[Exception], None] = lambda e: None


class SimpleWorkflowEngine:
    """简化版拆书工作流引擎。"""

    def __init__(
        self,
        config: NovelUnpackConfig,
        llm_client: LLMClient,
        prompt_mgr: PromptManager,
        search_svc: SearchService,
        callbacks: Optional[SimpleWorkflowCallbacks] = None,
    ) -> None:
        self.config = config
        self.llm = llm_client
        self.prompts = prompt_mgr
        self.search = search_svc
        self.callbacks = callbacks or SimpleWorkflowCallbacks()
        self._running = False
        self._selected_result: Optional[SearchResult] = None
        self._report_content = ""

    @property
    def is_running(self) -> bool:
        return self._running

    def run_search(self) -> None:
        """执行搜索步骤。"""
        self._running = True
        ensure_directories()

        try:
            self._log("🔍 [步骤 1/5] 搜索书籍...", "step")
            self._update_status(f"正在搜索「{self.config.novel_name}」...")

            # 直接使用用户输入的关键词搜索
            search_query = self.config.novel_name
            self._log(f"  搜索词：{search_query}", "info")

            # 执行搜索
            results = self.search.search(search_query, count=5)
            self._log(f"  找到 {len(results)} 条结果", "info")
            
            # 通知界面显示搜索结果
            self.callbacks.on_search_results(results)

        except Exception as exc:
            self._log(f"❌ 搜索失败：{exc}", "error")
            logger.exception("Search error")
            self.callbacks.on_error(exc)
            self._running = False
            raise

    def select_and_unpack(self, selected_index: int, results: list[SearchResult], 
                         selected_features: Optional[list[str]] = None) -> None:
        """选择书籍并开始拆解。"""
        if not self._running:
            self._running = True
        
        saved_files = []
        
        # 默认选择所有功能
        if selected_features is None:
            selected_features = ["overview", "characters", "plot", "worldview", 
                               "timeline", "writing", "emotion", "review"]
        
        # 功能映射
        feature_map = {
            "overview": ("小说概览", "01_小说概览.md"),
            "characters": ("人物图鉴", "02_人物图鉴与关系网.md"),
            "plot": ("情节结构", "03_情节结构与伏笔.md"),
            "worldview": ("世界观", "04_世界观设定集.md"),
            "timeline": ("故事线", "05_故事线与节奏.md"),
            "writing": ("写作技法", "06_写作技法与金句.md"),
            "emotion": ("情感弧线", "07_情感弧线与主题.md"),
            "review": ("综合评价", "08_综合评价.md"),
        }

        try:
            # 获取选中的书籍
            if 1 <= selected_index <= len(results):
                self._selected_result = results[selected_index - 1]
            else:
                self._selected_result = results[0] if results else None
            
            if not self._selected_result:
                raise ValueError("没有找到有效的书籍")
            
            book_title = self._selected_result.title
            author = self._selected_result.author
            
            self._log(f"✅ 已选择：《{book_title}》", "success")
            self._update_status(f"正在拆解《{book_title}》...")

            # 步骤 2: 提取书名和作者
            self._log("\n📝 [步骤 2/5] 提取书名信息...", "step")
            self._update_status("提取书名信息...")

            prompt = self.prompts.format(
                "03_extract_title.txt",
                search_result=f"1. 《{book_title}》 - {author}",
                selected_index=1,
            )
            result = self.llm.chat(
                messages=[
                    {"role": "system", "content": "从搜索结果中精确提取书名和作者。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=100,
            )

            # 解析结果
            title_match = None
            author_match = None
            for line in result.split("\n"):
                if "书名" in line:
                    title_match = line.replace("书名：", "").strip().strip("《》")
                elif "作者" in line:
                    author_match = line.replace("作者：", "").strip()
            
            self.config.novel_title = title_match or book_title
            self.config.author = author_match or author or "未知"

            self._log(f"  书名：《{self.config.novel_title}》", "info")
            self._log(f"  作者：{self.config.author}", "info")

            # 步骤 3: 生成拆解报告
            self._log("\n✍️ [步骤 3/5] 生成拆解报告...", "step")
            self._update_status("AI 正在生成拆解报告...")

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

            self._report_content = report
            char_count = len(report)
            mermaid_count = report.count("```mermaid")

            self._log(f"  ✅ 报告生成完成！", "success")
            self._log(f"  总字数：约{char_count}字", "info")
            self._log(f"  包含 {mermaid_count} 个 Mermaid 图表", "info")

            # 步骤 4: 拆分报告为多个文件（根据选择的功能）
            self._log("\n📦 [步骤 4/5] 拆分报告...", "step")
            self._update_status("拆分报告中...")
            
            # 创建输出目录
            book_dir = OUTPUT_DIR / self.config.novel_title.replace(":", "_").replace("/", "_")
            book_dir.mkdir(parents=True, exist_ok=True)
            
            # 按选择的功能保存报告文件
            prev_feature = None
            for feature_key in selected_features:
                if feature_key in feature_map:
                    section_name, filename = feature_map[feature_key]
                    next_feature = None
                    # 获取下一个功能用于截取
                    idx = list(feature_map.keys()).index(feature_key)
                    if idx < len(feature_map) - 1:
                        next_feature_key = list(feature_map.keys())[idx + 1]
                        if next_feature_key in feature_map:
                            next_feature = feature_map[next_feature_key][0]
                    
                    # 提取内容并保存
                    content = self._extract_section(report, section_name, next_feature)
                    file_path = book_dir / filename
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content or f"# {section_name}\n\n暂无内容")
                    saved_files.append(str(file_path))
                    self._log(f"  ✅ 已保存：{filename}", "success")
                    prev_feature = section_name

            # 步骤 5: 保存完整报告
            self._log("\n💾 [步骤 5/5] 保存完整报告...", "step")
            self._update_status("保存报告中...")

            # 保存主报告
            main_file = book_dir / "拆解报告.md"
            with open(main_file, "w", encoding="utf-8") as f:
                f.write(report)
            saved_files.append(str(main_file))
            
            self._log(f"  ✅ 完整报告已保存：拆解报告.md", "success")

            # 完成回调
            self.callbacks.on_finished(saved_files, book_dir)
            self._update_status("拆解完成 ✅")

        except Exception as exc:
            self._log(f"❌ 拆解失败：{exc}", "error")
            logger.exception("Unpack error")
            self.callbacks.on_error(exc)
            raise
        finally:
            self._running = False

    def _extract_section(self, report: str, start_keyword: str, end_keyword: str) -> str:
        """从报告中提取指定章节内容。"""
        lines = report.split("\n")
        in_section = False
        section_lines = []
        
        for line in lines:
            # 检查是否进入目标章节
            if not in_section and (start_keyword in line or f"## {start_keyword}" in line or f"### {start_keyword}" in line):
                in_section = True
                section_lines.append(line)
            # 检查是否离开目标章节
            elif in_section and end_keyword and (end_keyword in line or f"## {end_keyword}" in line or f"### {end_keyword}" in line):
                break
            # 在章节内
            elif in_section:
                section_lines.append(line)
        
        return "\n".join(section_lines)

    def _split_report(self, report: str) -> dict[str, str]:
        """拆分报告为多个部分。"""
        sections = {
            "小说概览": "",
            "人物图鉴": "",
            "情节结构": "",
            "世界观": "",
            "故事线": "",
            "写作技法": "",
            "情感弧线": "",
            "综合评价": "",
        }
        
        current_section = None
        lines = report.split("\n")
        
        for line in lines:
            for section_name in sections.keys():
                if line.startswith(f"## {section_name}") or line.startswith(f"### {section_name}"):
                    current_section = section_name
                    if not sections[section_name]:
                        sections[section_name] = line + "\n"
                    break
            else:
                if current_section:
                    sections[current_section] += line + "\n"
        
        return sections

    def stop(self) -> None:
        """停止工作流。"""
        self._running = False
        self._log("⏹ 工作流已停止", "warn")

    def _log(self, message: str, tag: str = "info") -> None:
        """记录日志。"""
        logger.info(f"[{tag}] {message}")
        self.callbacks.on_log(message, tag)

    def _update_status(self, status: str) -> None:
        """更新状态。"""
        self.callbacks.on_status(status)
