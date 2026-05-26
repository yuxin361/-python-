"""
配置管理模块 - 集中管理所有路径、环境变量、API 配置。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final


# ===================== 路径定义 =====================

BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent
PROMPTS_DIR: Final[Path] = BASE_DIR / "prompts"
OUTPUT_DIR: Final[Path] = BASE_DIR / "output"
HISTORY_DIR: Final[Path] = BASE_DIR / "history"
SRC_DIR: Final[Path] = BASE_DIR / "src"

# ===================== API Key 环境变量优先级 =====================

API_KEY_ENV_VARS: Final[list[str]] = [
    "OPENAI_API_KEY",
    "DASHSCOPE_API_KEY",
    "DEEPSEEK_API_KEY",
    "ARK_API_KEY",
    "MODEL_AGENT_API_KEY",
]

# ===================== 深度级别配置 =====================

DEPTH_CONFIG: Final[dict[int, dict]] = {
    1: {
        "label": "精要",
        "description": "简洁版，聚焦核心框架和关键人物",
        "max_tokens": 12000,
        "content_multiplier": 0.6,
    },
    2: {
        "label": "标准",
        "description": "均衡版，8 大模块完整展开，适合大多数场景",
        "max_tokens": 16384,
        "content_multiplier": 1.0,
    },
    3: {
        "label": "深入",
        "description": "详尽版，各模块内容量加倍，图表更丰富",
        "max_tokens": 24000,
        "content_multiplier": 1.8,
    },
}

# ===================== 默认值 =====================

DEFAULT_MODEL: Final[str] = "qwen-turbo"
DEFAULT_API_BASE: Final[str] = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 阿里云百炼 API 配置
# API Key: 从阿里云百炼控制台获取（sk- 开头）
# API Base: https://dashscope.aliyuncs.com/compatible-mode/v1
# 模型列表: qwen-turbo, qwen-plus, qwen-max, qwen-vision
DEFAULT_DEPTH: Final[int] = 2
DEFAULT_CHART_COUNT: Final[int] = 4

# ===================== 输出文件命名 =====================

OUTPUT_FILES: Final[list[str]] = [
    "01_小说概览.md",
    "02_人物图鉴与关系网.md",
    "03_情节结构与伏笔.md",
    "04_世界观设定集.md",
    "05_故事线与节奏.md",
    "06_写作技法与金句.md",
    "07_情感弧线与主题.md",
    "08_综合评价.md",
]

OUTPUT_MODULE_TITLES: Final[list[str]] = [
    "小说概览",
    "人物图鉴与关系网",
    "情节结构与伏笔回收",
    "世界观设定集",
    "故事线与叙事节奏",
    "写作技法与金句",
    "情感弧线与主题",
    "综合评价",
]


def load_dotenv_if_available() -> None:
    """尝试加载 .env 文件，如果 python-dotenv 可用的话。"""
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            pass


def get_api_key() -> str:
    """按优先级获取第一个可用的 API Key。"""
    for var_name in API_KEY_ENV_VARS:
        candidate = os.environ.get(var_name, "")
        if candidate:
            return candidate
    return ""


def get_bing_api_key() -> str:
    return os.environ.get("BING_SEARCH_API_KEY", "")


def get_api_base() -> str:
    return os.environ.get("OPENAI_API_BASE", DEFAULT_API_BASE)


def get_llm_model() -> str:
    return os.environ.get("LLM_MODEL", DEFAULT_MODEL)


def ensure_directories() -> None:
    """确保所有必要的目录存在。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)