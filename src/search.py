"""
搜索服务模块 - 搜索引擎接口与模拟搜索。

支持 Bing Search API、大语言模型搜索和模拟模式。
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.models import SearchResult
from src.llm import LLMClient
from src.config import get_api_key, get_api_base, get_llm_model

logger = logging.getLogger("novel_unpack.search")


class SearchService:
    """小说搜索服务。

    优先使用 Bing Search API，其次使用大语言模型搜索，最后使用模拟搜索。
    """

    def __init__(self, bing_api_key: str = "", mock_mode: bool = False, 
                 llm_api_key: str = "", llm_api_base: str = "", llm_model: str = "") -> None:
        self.bing_api_key = bing_api_key
        self.mock_mode = mock_mode
        
        # 创建 LLM 客户端（优先使用传入的配置，否则从环境变量读取）
        api_key = llm_api_key or get_api_key()
        api_base = llm_api_base or get_api_base()
        model = llm_model or get_llm_model()
        
        if api_key:
            self.llm = LLMClient(api_key=api_key, api_base=api_base, model=model)
        else:
            self.llm = None

    def search(self, query: str, count: int = 5) -> list[SearchResult]:
        """执行搜索。

        Args:
            query: 搜索关键词
            count: 期望返回的结果数量

        Returns:
            搜索结果列表
        """
        # 优先使用模拟模式
        if self.mock_mode:
            logger.info("使用模拟搜索: %s", query)
            return self._mock_search(query, count)
            
        if self.bing_api_key:
            logger.info("使用 Bing Search API 搜索: %s", query)
            return self._bing_search(query, count)

        # 使用大语言模型进行搜索（如果可用）
        if self.llm:
            logger.info("使用 LLM 搜索: %s", query)
            return self._llm_search(query, count)

        logger.info("使用模拟搜索（未配置 API Key）: %s", query)
        return self._mock_search(query, count)

    def _bing_search(self, query: str, count: int) -> list[SearchResult]:
        """调用 Bing Search API v7.0 进行搜索。"""
        try:
            import requests
        except ImportError:
            logger.warning("requests 库未安装，回退到模拟搜索")
            return self._mock_search(query, count)

        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {"Ocp-Apim-Subscription-Key": self.bing_api_key}
        params = {"q": query, "count": count, "mkt": "zh-CN"}

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Bing Search 请求失败: %s，回退到模拟搜索", exc)
            return self._mock_search(query, count)

        results: list[SearchResult] = []
        for i, item in enumerate(data.get("webPages", {}).get("value", []), 1):
            name = item.get("name", "")
            snippet = item.get("snippet", "")
            results.append(
                SearchResult(
                    index=i,
                    title=name,
                    author=self._extract_author(name, snippet),
                    description=snippet[:150],
                )
            )

        return results if results else self._mock_search(query, count)

    @staticmethod
    def _extract_author(text: str, snippet: str = "") -> str:
        """从文本中提取作者名。"""
        combined = text + " " + snippet
        patterns = [
            r"作者[：:]\s*(\S+)",
            r"(\S+)(?:著|作|写|编)",
            r"(\S+)/著",
        ]
        for pattern in patterns:
            match = re.search(pattern, combined)
            if match:
                return match.group(1)
        return ""

    def _llm_search(self, query: str, count: int) -> list[SearchResult]:
        """使用大语言模型进行搜索。

        当未配置 Bing API Key 时使用 LLM 生成书籍信息。
        """
        try:
            prompt = f"""请提供关于小说《{query}》的详细信息，以JSON格式输出，包含书籍的基本信息和简介。
            
要求输出格式：
[
  {{
    "title": "书籍标题",
    "author": "作者",
    "description": "书籍简介（100-150字）"
  }}
]

如果有多版本，请提供2-3个最相关的结果。
"""
            result_text = self.llm.chat(
                messages=[
                    {"role": "system", "content": "你是一个专业的书籍信息查询助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            import json
            result_text = result_text.strip()
            
            # 清理可能的markdown代码块标记
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            
            data = json.loads(result_text.strip())
            
            results = []
            for i, item in enumerate(data[:count], 1):
                results.append(
                    SearchResult(
                        index=i,
                        title=item.get("title", f"{query}"),
                        author=item.get("author", ""),
                        description=item.get("description", "暂无简介")[:150],
                    )
                )
            
            return results if results else self._mock_search(query, count)
            
        except Exception as exc:
            logger.warning("LLM 搜索失败: %s，回退到模拟搜索", exc)
            return self._mock_search(query, count)

    @staticmethod
    def _mock_search(query: str, count: int = 5) -> list[SearchResult]:
        """模拟搜索返回。

        当未配置 API Key 或搜索失败时使用。
        """
        return [
            SearchResult(
                index=1,
                title=query,
                author="",
                description="模拟搜索模式。配置 DASHSCOPE_API_KEY 环境变量可启用真实搜索。",
            ),
            SearchResult(
                index=2,
                title=f"{query}（完整版）",
                author="",
                description="模拟结果 - 请安装 python-dotenv 并配置 DASHSCOPE_API_KEY",
            ),
        ]