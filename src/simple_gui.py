"""
小说拆解助手 GUI - 支持书籍卡片展示和功能选项配置。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from tkinter import (
    Tk, ttk, StringVar, BooleanVar, IntVar, messagebox, Button, Checkbutton,
    Label, Frame, Scrollbar, Canvas
)

from src.config import (
    OUTPUT_DIR,
    ensure_directories,
    load_dotenv_if_available,
    get_api_key,
    get_api_base,
    get_bing_api_key,
)
from src.models import NovelUnpackConfig, SearchResult
from src.llm import LLMClient
from src.prompt_manager import PromptManager
from src.search import SearchService
from src.simple_workflow import SimpleWorkflowEngine, SimpleWorkflowCallbacks

logger = logging.getLogger("novel_unpack.simple_gui")

# 八个拆解功能选项
UNPACK_FEATURES = [
    ("小说概览", "overview", "01_小说概览.md", "📖"),
    ("人物图鉴", "characters", "02_人物图鉴与关系网.md", "👥"),
    ("情节结构", "plot", "03_情节结构与伏笔.md", "📊"),
    ("世界观", "worldview", "04_世界观设定集.md", "🌍"),
    ("故事线", "timeline", "05_故事线与节奏.md", "⏱️"),
    ("写作技法", "writing", "06_写作技法与金句.md", "✍️"),
    ("情感弧线", "emotion", "07_情感弧线与主题.md", "💖"),
    ("综合评价", "review", "08_综合评价.md", "⭐"),
]

# 热门大模型配置
MODEL_CONFIGS = {
    "阿里云通义千问": {
        "models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-max-longcontext"],
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "icon": "🇨🇳"
    },
    "OpenAI": {
        "models": ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4-turbo"],
        "api_base": "https://api.openai.com/v1",
        "icon": "🇺🇸"
    },
    "百度文心一言": {
        "models": ["ERNIE-Bot-4.0", "ERNIE-Bot-3.0", "ERNIE-Bot", "ERNIE-Bot-turbo"],
        "api_base": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        "icon": "🇨🇳"
    },
    "腾讯混元大模型": {
        "models": ["hunyuan-standard", "hunyuan-pro"],
        "api_base": "https://hunyuan.tencentcloudapi.com/",
        "icon": "🇨🇳"
    },
    "字节跳动豆包": {
        "models": ["Doubao", "Doubao-pro"],
        "api_base": "https://api.doubao.com/v1/chat/completions",
        "icon": "🇨🇳"
    },
    "Google Gemini": {
        "models": ["gemini-pro", "gemini-pro-vision"],
        "api_base": "https://generativelanguage.googleapis.com/v1",
        "icon": "🇺🇸"
    },
    "Anthropic Claude": {
        "models": ["claude-3-sonnet", "claude-3-opus", "claude-3-haiku", "claude-2.1"],
        "api_base": "https://api.anthropic.com/v1",
        "icon": "🇺🇸"
    },
}


class SimpleNovelUnpackGUI:
    """小说拆解助手 GUI。"""

    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("📚 小说拆解助手")
        # 调整窗口大小，确保所有内容完整显示，同时不会被任务栏遮挡
        self.root.geometry("1080x680")
        self._center_window()

        # 状态变量
        self.current_search_results: list[SearchResult] = []
        self.selected_result: Optional[SearchResult] = None
        self.workflow: Optional[SimpleWorkflowEngine] = None
        self.is_searching = False
        self.is_unpacking = False
        self.current_step = 0
        self.total_steps = 5
        self.selected_card = None
        self.action_buttons = None

        # 配置变量
        self.api_key_var = StringVar(value=get_api_key() or "")
        self.api_base_var = StringVar(value=get_api_base() or "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model_var = StringVar(value="qwen-turbo")
        self.provider_var = StringVar(value="阿里云通义千问")
        self.bing_api_key_var = StringVar(value=get_bing_api_key() or "")
        self.mock_mode_var = BooleanVar(value=False)
        self.chart_count_var = IntVar(value=4)
        
        # 功能选项（默认全选）
        self.feature_vars = {name: BooleanVar(value=True) for name, _, _, _ in UNPACK_FEATURES}

        # 创建布局
        self._create_widgets()

    def _center_window(self) -> None:
        """将窗口居中显示（考虑任务栏）。"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        
        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 使用正确的 Windows API 获取工作区（排除任务栏）
        try:
            from ctypes import windll, Structure, c_long, byref
            
            class RECT(Structure):
                _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]
            
            # SPI_GETWORKAREA = 48
            work_area = RECT()
            windll.user32.SystemParametersInfoA(48, 0, byref(work_area), 0)
            
            work_width = work_area.right - work_area.left
            work_height = work_area.bottom - work_area.top
            
            x = (work_width // 2) - (width // 2) + work_area.left
            y = (work_height // 2) - (height // 2) + work_area.top
            
        except Exception as e:
            logger.warning(f"获取工作区失败: {e}，使用备用方案")
            # 备用方案：预留底部任务栏空间（通常约40-50像素）
            available_height = screen_height - 50
            x = (screen_width // 2) - (width // 2)
            y = (available_height // 2) - (height // 2)
        
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _create_widgets(self) -> None:
        """创建所有控件。"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill="both", expand=True)

        # 左侧配置面板
        left_frame = ttk.Frame(main_frame, width=260)
        left_frame.pack(side="left", fill="y", padx=(0, 10))
        left_frame.pack_propagate(False)

        # API 配置
        config_group = ttk.LabelFrame(left_frame, text="⚙️ API 配置", padding=10)
        config_group.pack(fill="x", pady=(0, 10))

        ttk.Label(config_group, text="大模型 API Key", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        key_entry = ttk.Entry(config_group, textvariable=self.api_key_var, show="*", font=("Segoe UI", 10))
        key_entry.pack(fill="x", pady=(2, 8))

        # 服务提供商下拉列表
        ttk.Label(config_group, text="服务提供商", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        provider_names = [f"{config['icon']} {name}" for name, config in MODEL_CONFIGS.items()]
        provider_combo = ttk.Combobox(config_group, textvariable=self.provider_var, values=provider_names, 
                                     state="readonly", font=("Segoe UI", 10), width=22)
        provider_combo.pack(fill="x", pady=(2, 8))
        provider_combo.bind("<<ComboboxSelected>>", self._on_provider_change)

        # 大模型名称下拉列表
        ttk.Label(config_group, text="大模型名称", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.model_combo = ttk.Combobox(config_group, textvariable=self.model_var, 
                                       state="readonly", font=("Segoe UI", 10), width=22)
        self.model_combo.pack(fill="x", pady=(2, 8))

        # API Base 下拉列表
        ttk.Label(config_group, text="API Base", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.base_combo = ttk.Combobox(config_group, textvariable=self.api_base_var, 
                                       state="readonly", font=("Segoe UI", 10), width=22)
        self.base_combo.pack(fill="x", pady=(2, 8))

        # 模拟模式
        mock_check = Checkbutton(config_group, text="模拟模式", variable=self.mock_mode_var)
        mock_check.pack(anchor="w")
        
        # 初始化模型和 API Base 下拉列表
        self._update_model_and_base()

        # 当前状态
        status_group = ttk.LabelFrame(left_frame, text="📍 当前状态", padding=10)
        status_group.pack(fill="x")

        self.status_text = ttk.Label(status_group, text="就绪", font=("Segoe UI", 11), foreground="#4CAF50")
        self.status_text.pack(anchor="w")

        self.progress_bar = ttk.Progressbar(status_group, length=220, mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x", pady=5)
        
        self.progress_label = ttk.Label(status_group, text="0%", font=("Segoe UI", 9))
        self.progress_label.pack()

        # 右侧主区域
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True)

        # 右侧布局：左侧聊天区域，右侧拆解功能
        chat_frame = Frame(right_frame)
        chat_frame.pack(side="left", fill="both", expand=True)
        
        # 右侧配置面板（一列排布）
        features_frame = ttk.Frame(right_frame, width=180)
        features_frame.pack(side="right", fill="y")
        features_frame.pack_propagate(False)
        
        # 图表设置（在拆解功能上面）
        chart_group = ttk.LabelFrame(features_frame, text="📊 图表设置", padding=10)
        chart_group.pack(fill="x", pady=(5, 0))
        ttk.Label(chart_group, text="生成图表数量:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        chart_spin = ttk.Spinbox(chart_group, from_=1, to=10, textvariable=self.chart_count_var, 
                                font=("Segoe UI", 10), width=8)
        chart_spin.pack(anchor="w", pady=(2, 0))
        
        # 拆解功能
        features_group = ttk.LabelFrame(features_frame, text="📋 拆解功能", padding=10)
        features_group.pack(fill="x", pady=5)
        
        # 一列排布功能选项
        for name, key, filename, icon in UNPACK_FEATURES:
            cb_var = self.feature_vars[name]
            cb = Checkbutton(features_group, text=f"{icon} {name}", variable=cb_var, font=("SimHei", 10))
            cb.pack(anchor="w", pady=2)

        # 滚动条
        self.scrollbar = Scrollbar(chat_frame)
        self.scrollbar.pack(side="right", fill="y")

        # 消息容器（使用Canvas支持滚动）
        self.messages_canvas = Canvas(chat_frame, yscrollcommand=self.scrollbar.set)
        self.messages_canvas.pack(fill="both", expand=True)
        self.scrollbar.config(command=self.messages_canvas.yview)

        # 内部容器
        self.messages_frame = Frame(self.messages_canvas)
        self.messages_canvas.create_window((0, 0), window=self.messages_frame, anchor="nw")
        
        # 绑定滚动事件
        self.messages_frame.bind("<Configure>", lambda e: self.messages_canvas.configure(scrollregion=self.messages_canvas.bbox("all")))
        
        # 绑定鼠标滚轮事件（支持多个控件，确保事件传播）
        self.messages_canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.messages_frame.bind("<MouseWheel>", self._on_mouse_wheel_propagate)
        chat_frame.bind("<MouseWheel>", self._on_mouse_wheel)
        self.root.bind("<MouseWheel>", self._on_mouse_wheel_global)

        # 输入区域（放在聊天区域底部）
        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill="x", padx=5, pady=5)

        self.input_var = StringVar()
        self.input_entry = ttk.Entry(input_frame, textvariable=self.input_var, font=("SimHei", 12), width=60)
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.input_entry.bind("<Return>", lambda e: self._on_send())

        self.send_btn = Button(input_frame, text="🔍 搜索书籍", command=self._on_send, 
                              bg="#4CAF50", fg="white", padx=15, font=("Segoe UI", 11, "bold"))
        self.send_btn.pack(side="right")

        # 添加欢迎消息
        self._add_message("assistant", "欢迎使用小说拆解助手！\n\n📖 请输入小说名称开始搜索\n\n💡 提示：如果尚未配置 API Key，可以勾选左侧「模拟模式」来体验拆解功能。")

    def _add_message(self, sender: str, content: str) -> None:
        """添加消息到聊天区域。"""
        msg_frame = Frame(self.messages_frame)
        msg_frame.pack(fill="x", padx=5, pady=2)
        
        if sender == "user":
            Label(msg_frame, text=f"👤 你：", font=("SimHei", 11), fg="#1976D2").pack(anchor="w")
            Label(msg_frame, text=content, font=("SimHei", 11), fg="#333", justify="left").pack(anchor="w", padx=(20, 0))
        else:
            Label(msg_frame, text=f"🤖 拆解助手：", font=("SimHei", 11), fg="#4CAF50").pack(anchor="w")
            Label(msg_frame, text=content, font=("SimHei", 11), fg="#333", justify="left").pack(anchor="w", padx=(20, 0))
        
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        """滚动到底部。"""
        self.messages_canvas.update_idletasks()
        self.messages_canvas.yview_moveto(1.0)

    def _on_mouse_wheel(self, event):
        """处理鼠标滚轮事件。"""
        self.messages_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mouse_wheel_propagate(self, event):
        """处理鼠标滚轮事件并传播到 Canvas（用于内部 Frame）。"""
        self.messages_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        event.widget.nametowidget(event.widget.winfo_parent()).event_generate("<MouseWheel>", delta=event.delta)

    def _on_mouse_wheel_global(self, event):
        """全局鼠标滚轮处理 - 当鼠标在聊天区域时滚动。"""
        # 获取鼠标位置
        x, y = event.x, event.y
        
        # 获取聊天区域的位置和大小
        chat_x = self.messages_canvas.winfo_rootx()
        chat_y = self.messages_canvas.winfo_rooty()
        chat_width = self.messages_canvas.winfo_width()
        chat_height = self.messages_canvas.winfo_height()
        
        # 检查鼠标是否在聊天区域内
        if chat_x <= x <= chat_x + chat_width and chat_y <= y <= chat_y + chat_height:
            self.messages_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _show_search_results(self, results: list[SearchResult]) -> None:
        """显示搜索结果（在聊天框内显示带样式的卡片）。"""
        self.current_search_results = results
        
        # 移除之前的操作按钮
        if self.action_buttons and self.action_buttons.winfo_exists():
            self.action_buttons.destroy()
            self.action_buttons = None
        
        # 取消之前选中的卡片
        if self.selected_card:
            self.selected_card.config(borderwidth=1)
            self.selected_card = None
        
        if not results:
            self._add_message("assistant", "😔 没有找到匹配的书籍")
            return

        # 在聊天区域显示结果（卡片样式）
        self._add_message("assistant", f"🔍 找到 {len(results)} 个匹配结果：")
        
        for idx, result in enumerate(results, 1):
            # 创建书籍卡片框架
            card = Frame(self.messages_frame, borderwidth=2, relief="solid", bg="#fff", padx=10, pady=8)
            card.pack(fill="x", padx=5, pady=5)
            card.config(cursor="hand2")

            # 创建点击处理函数
            def on_card_click(e, r=result, c=card):
                self._on_select_result(r, c)

            # 序号和书名（绿色）- 绑定点击事件
            title_label = Label(card, text=f"【{idx}】《{result.title}》{' - ' + result.author if result.author else ''}", 
                              font=("SimHei", 12, "bold"), fg="#2E7D32", bg="#fff", anchor="w")
            title_label.pack(fill="x")
            title_label.bind("<Button-1>", on_card_click)
            title_label.config(cursor="hand2")

            # 分割线
            separator = Frame(card, height=1, bg="#E0E0E0")
            separator.pack(fill="x", pady=4)

            # 简介区域（深灰色）- 绑定点击事件
            desc_text = result.description[:120] + "..." if len(result.description) > 120 else result.description
            desc_label = Label(card, text=f"📝 {desc_text}", 
                             font=("SimHei", 10), fg="#616161", bg="#fff", anchor="w", wraplength=700)
            desc_label.pack(fill="x", pady=(0, 4))
            desc_label.bind("<Button-1>", on_card_click)
            desc_label.config(cursor="hand2")

            # 点击提示（浅灰色）- 绑定点击事件
            hint_label = Label(card, text="💡 点击此卡片选择书籍", 
                              font=("SimHei", 9, "italic"), fg="#9E9E9E", bg="#fff", anchor="w")
            hint_label.pack(fill="x")
            hint_label.bind("<Button-1>", on_card_click)
            hint_label.config(cursor="hand2")
        
        self._scroll_to_bottom()

    def _on_select_result(self, result: SearchResult, card: Frame) -> None:
        """选择书籍后的操作 - 显示开始拆解和重新选择按钮在卡片下方。"""
        # 移除之前的操作按钮
        if self.action_buttons and self.action_buttons.winfo_exists():
            self.action_buttons.destroy()
        
        # 取消之前选中的卡片样式（恢复默认）
        if self.selected_card and self.selected_card != card:
            self.selected_card.config(borderwidth=2, bg="#ffffff", highlightbackground="#E0E0E0")
        
        # 设置当前选中卡片样式（明显的视觉效果）
        card.config(borderwidth=3, bg="#E8F5E9", highlightbackground="#4CAF50", highlightthickness=3)
        
        self.selected_result = result
        self.selected_card = card
        
        # 在选中卡片下方创建操作按钮
        self.action_buttons = Frame(self.messages_frame)
        self.action_buttons.pack(fill="x", padx=5, pady=3)
        
        # 开始拆解按钮
        unpack_btn = Button(self.action_buttons, text="🚀 开始拆解", 
                           command=self._start_unpack, 
                           bg="#4CAF50", fg="white", padx=25, pady=5, 
                           font=("SimHei", 11, "bold"), relief="raised")
        unpack_btn.pack(side="left", padx=5)
        
        # 重新选择按钮
        reselect_btn = Button(self.action_buttons, text="🔄 重新选择", 
                             command=self._reset_selection, 
                             bg="#f44336", fg="white", padx=25, pady=5, 
                             font=("SimHei", 11), relief="raised")
        reselect_btn.pack(side="left", padx=5)
        
        self._scroll_to_bottom()

    def _reset_selection(self) -> None:
        """重置选择。"""
        self.selected_result = None
        
        # 移除操作按钮
        if self.action_buttons and self.action_buttons.winfo_exists():
            self.action_buttons.destroy()
            self.action_buttons = None
        
        # 恢复卡片样式（取消选中状态）
        if self.selected_card:
            self.selected_card.config(borderwidth=2, bg="#ffffff", highlightbackground="#E0E0E0")
            self.selected_card = None
        
        self._add_message("assistant", "请重新输入小说名称进行搜索。")

    def _on_send(self) -> None:
        """发送按钮点击事件。"""
        query = self.input_var.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入小说名称")
            return
        
        # 检查 API Key 是否配置（模拟模式除外）
        if not self.mock_mode_var.get():
            api_key = self.api_key_var.get().strip()
            if not api_key:
                messagebox.showwarning("提示", "请先配置大模型 API Key！\n\n在左侧「API 配置」区域输入您的 API Key。")
                return
        
        if self.is_searching or self.is_unpacking:
            messagebox.showwarning("提示", "正在处理中，请稍候")
            return

        self.input_var.set("")
        self._add_message("user", query)
        self._start_search(query)

    def _start_search(self, query: str) -> None:
        """开始搜索。"""
        self.is_searching = True
        self.send_btn.config(state="disabled")
        self._update_status("搜索书籍...", 1)

        def search_thread():
            try:
                config = self._create_config(query)
                llm = LLMClient(config.api_key, config.api_base, config.llm_model, use_mock=self.mock_mode_var.get())
                prompts = PromptManager()
                search = SearchService(
                    bing_api_key=self.bing_api_key_var.get(), 
                    mock_mode=self.mock_mode_var.get(),
                    llm_api_key=self.api_key_var.get(),
                    llm_api_base=self.api_base_var.get(),
                    llm_model=self.model_var.get()
                )
                
                callbacks = SimpleWorkflowCallbacks(
                    on_log=self._on_workflow_log,
                    on_status=self._update_status,
                    on_search_results=self._show_search_results,
                    on_error=self._on_workflow_error,
                    on_finished=self._on_workflow_finished,
                )
                
                self.workflow = SimpleWorkflowEngine(config, llm, prompts, search, callbacks)
                self.workflow.run_search()
                
            finally:
                self.is_searching = False
                self.send_btn.config(state="normal")

        threading.Thread(target=search_thread, daemon=True).start()

    def _start_unpack(self) -> None:
        """开始拆解。"""
        if not self.selected_result or not self.workflow:
            messagebox.showwarning("提示", "请先选择一本书籍")
            return

        self.is_unpacking = True
        
        # 移除操作按钮
        if self.action_buttons and self.action_buttons.winfo_exists():
            self.action_buttons.destroy()
            self.action_buttons = None
        
        self._update_status("提取书名信息...", 2)

        def unpack_thread():
            try:
                self.workflow.select_and_unpack(
                    self.current_search_results.index(self.selected_result) + 1,
                    self.current_search_results,
                    self._get_selected_features()
                )
                
            finally:
                self.is_unpacking = False
                self.send_btn.config(state="normal")

        threading.Thread(target=unpack_thread, daemon=True).start()

    def _get_selected_features(self) -> list[str]:
        """获取选中的功能列表。"""
        selected = []
        for name, key, filename, icon in UNPACK_FEATURES:
            if self.feature_vars[name].get():
                selected.append(key)
        return selected

    def _create_config(self, novel_name: str) -> NovelUnpackConfig:
        """创建配置对象。"""
        return NovelUnpackConfig(
            novel_name=novel_name,
            depth=2,
            chart_count=self.chart_count_var.get(),
            api_key=self.api_key_var.get(),
            api_base=self.api_base_var.get(),
            llm_model="qwen-turbo",
            output_dir=OUTPUT_DIR,
        )

    def _update_status(self, status: str, step: int = 0) -> None:
        """更新状态显示。"""
        self.status_text.config(text=status)
        if step > 0:
            self.current_step = step
            progress = int((step / self.total_steps) * 100)
            self.progress_bar["value"] = progress
            self.progress_label.config(text=f"{progress}% ({step}/{self.total_steps})")

    def _on_workflow_log(self, message: str, tag: str) -> None:
        """工作流日志回调。"""
        if tag == "error":
            self._add_message("assistant", f"❌ {message}")
        elif tag == "success":
            self._add_message("assistant", f"✅ {message}")
        elif tag == "warn":
            self._add_message("assistant", f"⚠️ {message}")
        elif "步骤" in message:
            import re
            match = re.search(r'步骤 (\d+)/(\d+)', message)
            if match:
                step = int(match.group(1))
                total = int(match.group(2))
                self.total_steps = total
                progress = int((step / total) * 100)
                self.progress_bar["value"] = progress
                self.progress_label.config(text=f"{progress}% ({step}/{total})")
            self._add_message("assistant", message)
        else:
            self._add_message("assistant", message)

    def _on_workflow_error(self, exc: Exception) -> None:
        """工作流错误回调。"""
        self._add_message("assistant", f"❌ 发生错误：{str(exc)}")
        self.is_searching = False
        self.is_unpacking = False
        self.send_btn.config(state="normal")
        self.progress_bar["value"] = 0

    def _on_workflow_finished(self, saved_files: list[str], book_dir: Path) -> None:
        """工作流完成回调。"""
        self.progress_bar["value"] = 100
        self.progress_label.config(text="100%")
        self._add_message("assistant", f"🎉 拆解完成！报告已保存到：\n{book_dir}")
        
        if saved_files:
            file_list = "\n".join([f"  - {Path(f).name}" for f in saved_files])
            self._add_message("assistant", f"📁 保存的文件：\n{file_list}")

    def _update_model_and_base(self) -> None:
        """更新模型和 API Base 下拉列表。"""
        # 获取当前选择的服务提供商（去掉图标）
        provider_name = self.provider_var.get()
        for icon_name, config in MODEL_CONFIGS.items():
            display_name = f"{config['icon']} {icon_name}"
            if display_name == provider_name:
                provider_name = icon_name
                break
        
        # 更新模型列表
        if provider_name in MODEL_CONFIGS:
            config = MODEL_CONFIGS[provider_name]
            self.model_combo["values"] = config["models"]
            self.model_combo.set(config["models"][0])
            self.base_combo["values"] = [config["api_base"]]
            self.base_combo.set(config["api_base"])

    def _on_provider_change(self, event) -> None:
        """服务提供商变化时更新模型和 API Base。"""
        self._update_model_and_base()

    def run(self) -> None:
        """运行 GUI。"""
        load_dotenv_if_available()
        ensure_directories()
        self.root.mainloop()


if __name__ == "__main__":
    app = SimpleNovelUnpackGUI()
    app.run()
