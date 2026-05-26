"""
GUI 对话式界面模块 - 聊天风格的拆书工作流。

采用现代化聊天界面设计，支持：
- 对话式输入小说名称
- 搜索结果气泡展示
- 交互式书籍选择
- 实时拆解进度条
- 完成后一键保存
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from tkinter import (
    Tk, ttk, StringVar, IntVar, BooleanVar, Text, messagebox,
)
from tkinter.scrolledtext import ScrolledText
from typing import Any, Optional

from src.config import (
    PROMPTS_DIR,
    OUTPUT_DIR,
    ensure_directories,
    load_dotenv_if_available,
    get_api_key,
    get_api_base,
    get_llm_model,
    get_bing_api_key,
)
from src.models import NovelUnpackConfig, SearchResult
from src.llm import LLMClient
from src.prompt_manager import PromptManager
from src.search import SearchService
from src.workflow import WorkflowEngine, WorkflowCallbacks

logger = logging.getLogger("novel_unpack.gui")


class ChatMessage:
    """聊天消息对象。"""
    
    def __init__(self, sender: str, content: str, type: str = "text") -> None:
        self.sender = sender  # "user" or "assistant"
        self.content = content
        self.type = type      # "text", "search", "select", "progress", "result"
        self.timestamp = time.strftime("%H:%M")


class NovelUnpackChatGUI:
    """对话式拆书工作流 GUI。"""

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("📚 小说拆解助手")
        self.root.geometry("1000x650")
        self.root.minsize(900, 550)
        
        # 窗口居中显示
        self._center_window()

        load_dotenv_if_available()
        ensure_directories()

        # 初始化模拟模式变量（必须在 _build_llm_client 之前）
        self.mock_mode_var = BooleanVar(value=False)

        self.config = NovelUnpackConfig(novel_name="")
        self.prompt_mgr = PromptManager(PROMPTS_DIR)
        self.search_svc = SearchService(get_bing_api_key())
        self.llm_client = self._build_llm_client()
        self.engine: Optional[WorkflowEngine] = None
        self.chat_history: list[ChatMessage] = []

        self._setup_styles()
        self._build_ui()
        self._add_welcome_message()

    def _build_llm_client(self) -> LLMClient:
        """构建 LLM 客户端（支持模拟模式）。"""
        if self.mock_mode_var.get():
            return LLMClient("", "", "", use_mock=True)
        
        api_key = get_api_key()
        api_base = get_api_base()
        model = get_llm_model()
        if not api_key:
            try:
                return LLMClient("dummy", api_base, model)
            except ValueError:
                pass
        return LLMClient(api_key, api_base, model)

    def _on_mock_mode_change(self) -> None:
        """模拟模式切换回调。"""
        if hasattr(self, 'key_entry'):
            self.key_entry.config(state="disabled" if self.mock_mode_var.get() else "normal")
        # 重新构建 LLM 客户端
        self.llm_client = self._build_llm_client()

    def _center_window(self) -> None:
        """将窗口居中显示。"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"+{x}+{y}")

    def _setup_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        # 主题颜色
        bg_color = "#0d1117"
        sidebar_bg = "#161b22"
        chat_bg = "#0d1117"
        user_bubble = "#238636"
        assistant_bubble = "#21262d"
        accent = "#58a6ff"
        text_color = "#e6edf3"
        muted = "#8b949e"

        style.configure("TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color, foreground=text_color, font=("Segoe UI", 13))
        style.configure(
            "TButton",
            background=sidebar_bg,
            foreground=text_color,
            font=("Segoe UI", 12),
            padding=(12, 8),
            borderwidth=0,
        )
        style.map("TButton", 
                  background=[("active", accent)],
                  foreground=[("active", "white")])
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="white",
            font=("Segoe UI", 12, "bold"),
            padding=(16, 8),
        )
        style.map("Accent.TButton", background=[("active", "#1f6feb")])
        style.configure("Status.TLabel", font=("Segoe UI", 11), foreground=muted)
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground=text_color)

        self.root.configure(bg=bg_color)

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # 左侧配置面板
        left_panel = ttk.Frame(main_frame, width=280)
        left_panel.pack(side="left", fill="y")
        left_panel.pack_propagate(False)
        self._build_left_panel(left_panel)

        # 右侧聊天区域
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side="right", fill="both", expand=True)
        self._build_right_panel(right_panel)

    def _build_left_panel(self, parent: ttk.Frame) -> None:
        # 标题
        header = ttk.Label(parent, text="⚙️ 配置", style="Header.TLabel")
        header.pack(anchor="w", padx=16, pady=(16, 8))

        # API 配置区域
        config_frame = ttk.LabelFrame(parent, text="API 配置", padding=14)
        config_frame.pack(fill="x", padx=12, pady=(0, 10))

        # 模拟模式
        self.mock_mode_var = BooleanVar(value=False)
        mock_check = ttk.Checkbutton(
            config_frame, text="🔧 模拟模式（无需 API Key）",
            variable=self.mock_mode_var, command=self._on_mock_mode_change
        )
        mock_check.pack(anchor="w", pady=(0, 8))

        # API Key
        ttk.Label(config_frame, text="API Key", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.api_key_var = StringVar(value=get_api_key() or "")
        key_entry = ttk.Entry(config_frame, textvariable=self.api_key_var, show="*", font=("Segoe UI", 11))
        key_entry.pack(fill="x", pady=(2, 10))
        self.key_entry = key_entry

        # API Base URL - 默认阿里云百炼
        ttk.Label(config_frame, text="API Base", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        default_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.api_base_var = StringVar(value=get_api_base() or default_base)
        ttk.Entry(config_frame, textvariable=self.api_base_var, font=("Segoe UI", 11)).pack(fill="x", pady=(2, 8))

        # 分隔线
        ttk.Separator(parent).pack(fill="x", padx=12, pady=8)

        # 拆解参数
        param_frame = ttk.LabelFrame(parent, text="拆解参数", padding=14)
        param_frame.pack(fill="x", padx=12, pady=(0, 10))

        ttk.Label(param_frame, text="拆解深度", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 4))
        depth_frame = ttk.Frame(param_frame)
        depth_frame.pack(fill="x", pady=(0, 10))
        self.depth_var = IntVar(value=2)
        depths = [(1, "精要"), (2, "标准"), (3, "深入")]
        for val, label in depths:
            rb = ttk.Radiobutton(
                depth_frame, text=label, variable=self.depth_var, value=val,
                style="TRadiobutton"
            )
            rb.pack(side="left", padx=(0, 12))

        ttk.Label(param_frame, text="图表数量", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 4))
        self.chart_count_var = IntVar(value=4)
        spinbox = ttk.Spinbox(
            param_frame, from_=4, to=12, textvariable=self.chart_count_var,
            width=8, font=("Segoe UI", 11)
        )
        spinbox.pack(anchor="w")

        # 状态信息
        status_frame = ttk.LabelFrame(parent, text="当前状态", padding=14)
        status_frame.pack(fill="both", expand=True, padx=12)

        self.status_label = ttk.Label(status_frame, text="等待输入...", style="Status.TLabel")
        self.status_label.pack(anchor="w")

        self.progress_var = StringVar(value="0%")
        self.progress_bar = ttk.Progressbar(status_frame, mode="determinate", length=200)
        self.progress_bar.pack(fill="x", pady=8)
        ttk.Label(status_frame, textvariable=self.progress_var, style="Status.TLabel").pack(anchor="w")

    def _build_right_panel(self, parent: ttk.Frame) -> None:
        # 聊天区域
        chat_frame = ttk.Frame(parent)
        chat_frame.pack(fill="both", expand=True)

        # 聊天历史
        self.chat_history_text = ScrolledText(
            chat_frame, wrap="word", font=("Segoe UI", 13),
            bg="#0d1117", fg="#e6edf3", insertbackground="#58a6ff",
            relief="flat", borderwidth=0, highlightthickness=0,
            state="disabled"
        )
        self.chat_history_text.pack(fill="both", expand=True, padx=16, pady=16)

        # 输入区域 - 使用 pack(side="bottom") 确保始终显示在底部
        input_frame = ttk.Frame(parent, padding=12)
        input_frame.pack(side="bottom", fill="x")

        # 发送按钮
        self.send_btn = ttk.Button(
            input_frame, text="发送", style="Accent.TButton",
            command=self._send_message
        )
        self.send_btn.pack(side="right")

        # 输入框
        self.input_var = StringVar()
        self.input_entry = ttk.Entry(
            input_frame, textvariable=self.input_var, font=("Segoe UI", 13),
            width=80
        )
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.input_entry.bind("<Return>", lambda e: self._send_message())
        self.input_entry.focus_set()

    def _add_welcome_message(self) -> None:
        welcome = (
            "你好！我是你的小说拆解助手 📚\n\n"
            "请输入小说名称，我会帮你搜索并生成深度拆解报告。\n"
            "拆解报告包含：人物图鉴、情节结构、世界观设定、故事线分析等8大模块。\n\n"
            "🎯 功能特点：\n"
            "• 支持精要/标准/深入三种深度级别\n"
            "• 自动生成 Mermaid 可视化图表\n"
            "• 质量校验与自动补全\n"
            "• 一键保存为独立文件\n\n"
            "开始吧！输入一本小说名称 →"
        )
        self._add_message("assistant", welcome, "text")

    def _add_message(self, sender: str, content: str, type: str = "text") -> None:
        """添加消息到聊天历史。"""
        msg = ChatMessage(sender, content, type)
        self.chat_history.append(msg)
        
        self.chat_history_text.config(state="normal")
        
        # 时间戳
        self.chat_history_text.insert("end", f"\n{msg.timestamp} ", "timestamp")
        
        if sender == "user":
            # 用户消息
            self.chat_history_text.insert("end", "你\n", "sender_user")
            self.chat_history_text.insert("end", content, "bubble_user")
        else:
            # 助手消息
            self.chat_history_text.insert("end", "📚 拆解助手\n", "sender_assistant")
            self.chat_history_text.insert("end", content, "bubble_assistant")
        
        self.chat_history_text.insert("end", "\n\n")
        self.chat_history_text.config(state="disabled")
        self.chat_history_text.see("end")

        # 设置标签样式
        self.chat_history_text.tag_config("timestamp", foreground="#8b949e", font=("Segoe UI", 9))
        self.chat_history_text.tag_config("sender_user", foreground="#58a6ff", font=("Segoe UI", 12, "bold"))
        self.chat_history_text.tag_config("sender_assistant", foreground="#f0883e", font=("Segoe UI", 12, "bold"))
        self.chat_history_text.tag_config("bubble_user", background="#238636", foreground="white", lmargin1=12, lmargin2=12, rmargin=12)
        self.chat_history_text.tag_config("bubble_assistant", background="#21262d", foreground="#e6edf3", lmargin1=12, lmargin2=12, rmargin=12)
        self.chat_history_text.tag_config("search_result", foreground="#a5d6ff")
        self.chat_history_text.tag_config("progress", foreground="#3fb950")

    def _send_message(self) -> None:
        """发送用户消息，触发拆书流程。"""
        novel_name = self.input_var.get().strip()
        if not novel_name:
            return

        self._add_message("user", novel_name, "text")
        self.input_var.set("")
        self.send_btn.config(state="disabled")
        self.input_entry.config(state="disabled")

        self._update_status(f"正在搜索「{novel_name}」...")

        threading.Thread(target=self._run_workflow, args=(novel_name,), daemon=True).start()

    def _quick_select(self, book_name: str) -> None:
        """快捷选择书籍。"""
        self.input_var.set(book_name)
        self._send_message()

    def _run_workflow(self, novel_name: str) -> None:
        """运行拆书工作流。"""
        try:
            api_key = self.api_key_var.get() or get_api_key()
            if not api_key:
                self.root.after(0, lambda: self._show_error("请先配置 API Key"))
                return

            api_base = self.api_base_var.get() or get_api_base()
            model = get_llm_model()
            bing_key = get_bing_api_key()

            self.config = NovelUnpackConfig(
                novel_name=novel_name,
                depth=self.depth_var.get(),
                chart_count=self.chart_count_var.get(),
                api_base=api_base,
                api_key=api_key,
                llm_model=model,
            )

            self.llm_client = LLMClient(api_key, api_base, model, use_mock=self.mock_mode_var.get())
            self.search_svc = SearchService(bing_key)

            callbacks = WorkflowCallbacks(
                on_log=self._on_workflow_log,
                on_status=self._on_workflow_status,
                on_search_results=self._on_search_results,
                on_finished=self._on_workflow_finished,
                on_error=self._on_workflow_error,
            )

            self.engine = WorkflowEngine(
                config=self.config,
                llm_client=self.llm_client,
                prompt_mgr=self.prompt_mgr,
                search_svc=self.search_svc,
                callbacks=callbacks,
            )

            self.engine.run()

        except Exception as exc:
            self.root.after(0, lambda e=exc: self._on_workflow_error(e))

    def _on_workflow_log(self, message: str, tag: str) -> None:
        """工作流日志回调。"""
        if tag == "success":
            message = f"✅ {message}"
        elif tag == "error":
            message = f"❌ {message}"
        elif tag == "warn":
            message = f"⚠️ {message}"
        elif tag == "step":
            message = f"🔄 {message}"
        elif tag == "header":
            message = f"📌 {message}"
        
        self.root.after(0, lambda: self._add_message("assistant", message, "progress"))

    def _on_workflow_status(self, status: str) -> None:
        """工作流状态回调。"""
        self.root.after(0, lambda: self._update_status(status))

    def _on_search_results(self, results: list[SearchResult]) -> Optional[int]:
        """搜索结果回调 - 自动选择第一个结果。"""
        # 显示搜索结果
        result_text = f"🔍 找到 {len(results)} 个匹配结果：\n\n"
        for r in results:
            result_text += f"【{r.index}】《{r.title}》"
            if r.author:
                result_text += f" - {r.author}"
            if r.description:
                result_text += f"\n   {r.description}"
            result_text += "\n\n"
        
        self.root.after(0, lambda: self._add_message("assistant", result_text, "search"))
        
        # 自动选择第一个结果
        if results:
            selected = results[0]
            self.root.after(0, lambda: self._add_message("assistant", f"✅ 自动选择第一个结果：《{selected.title}》", "text"))
            return 1
        return 1

    def _on_workflow_finished(self, config: NovelUnpackConfig, saved_files: list[str], book_dir: Path) -> None:
        """工作流完成回调。"""
        def show_finish():
            result_text = (
                f"🎉 《{config.novel_title}》拆解完成！\n\n"
                f"📂 输出目录：{book_dir}\n\n"
                f"📄 生成的文件：\n"
            )
            for f in saved_files:
                result_text += f"   • {f}\n"
            
            result_text += f"\n💡 提示：可在 Typora / VS Code 中查看 Mermaid 图表渲染效果"
            
            self._add_message("assistant", result_text, "result")
            
            # 添加打开文件夹按钮
            def open_folder():
                os.startfile(book_dir)
            
            self.open_btn = ttk.Button(
                self.chat_history_text.master,
                text="📂 打开输出文件夹",
                style="Accent.TButton",
                command=open_folder
            )
            self.open_btn.pack(pady=(0, 8))
            
            self._update_status("拆解完成 ✅")
            self._reset_progress()
            self.send_btn.config(state="normal")
            self.input_entry.config(state="normal")
        
        self.root.after(0, show_finish)

    def _on_workflow_error(self, exc: Exception) -> None:
        """工作流错误回调。"""
        def show_error():
            error_msg = f"❌ 拆解过程中出现错误：\n\n{str(exc)}"
            self._add_message("assistant", error_msg, "text")
            self._update_status("出错了 ❌")
            self._reset_progress()
            self.send_btn.config(state="normal")
            self.input_entry.config(state="normal")
        
        self.root.after(0, show_error)

    def _show_error(self, message: str) -> None:
        """显示错误消息。"""
        self._add_message("assistant", f"❌ {message}", "text")
        messagebox.showerror("错误", message)
        self.send_btn.config(state="normal")
        self.input_entry.config(state="normal")

    def _update_status(self, text: str) -> None:
        """更新状态标签。"""
        self.status_label.config(text=text)

    def _reset_progress(self) -> None:
        """重置进度条。"""
        self.progress_bar["value"] = 0
        self.progress_var.set("0%")


def main() -> None:
    """启动聊天式 GUI。"""
    root = Tk()
    NovelUnpackChatGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()