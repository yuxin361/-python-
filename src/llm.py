"""
LLM API 客户端模块 - 统一的大模型调用接口。

支持所有兼容 OpenAI Chat Completion API 格式的模型：
- OpenAI GPT-4o / GPT-4
- Anthropic Claude (via API proxy)
- DeepSeek
- 通义千问 (DashScope)
- DeepSeek

配置方式（按优先级）：
1. 环境变量
2. 构造函数参数
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger("novel_unpack.llm")


class MockLLMClient:
    """模拟 LLM 客户端 - 用于测试和演示。"""

    def __init__(self) -> None:
        self.model = "mock"

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 16384,
        timeout: int = 300,
    ) -> str:
        """返回模拟响应。"""
        last_message = messages[-1]["content"] if messages else ""
        
        # 模拟搜索关键词生成
        if "搜索关键词" in last_message or "优化" in last_message:
            return "三体 小说 简介"
        
        # 模拟搜索结果
        if "搜索结果" in last_message or "搜索书籍" in last_message:
            return json.dumps([
                {"title": "三体", "link": "https://example.com/santi", "snippet": "刘慈欣创作的科幻小说"},
                {"title": "三体II：黑暗森林", "link": "https://example.com/santi2", "snippet": "三体系列第二部"},
                {"title": "三体III：死神永生", "link": "https://example.com/santi3", "snippet": "三体系列第三部"}
            ], ensure_ascii=False)
        
        # 模拟拆书报告生成
        if "拆解" in last_message or "分析" in last_message or "人物" in last_message:
            return """## 小说概览

**书名**: 《三体》
**作者**: 刘慈欣
**类型**: 科幻

## 人物图鉴

### 主要人物
- **叶文洁**: 红岸基地科学家
- **罗辑**: 面壁者
- **汪淼**: 纳米科学家

## 情节结构

故事分为三个部分，讲述了地球文明与三体文明的接触。

## 世界观设定

三体星系拥有三颗太阳，文明经历了多次毁灭与重生。"""
        
        # 默认响应
        return "这是一个模拟响应。在实际使用中，请配置有效的 API Key。"

    def chat_with_system(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16384,
    ) -> str:
        """简化的带 system prompt 的调用。"""
        return self.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )


class LLMClient:
    """统一的大模型 API 客户端。"""

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        use_mock: bool = False,
    ) -> None:
        if use_mock:
            self._client = MockLLMClient()
            return
            
        if not api_key:
            raise ValueError(
                "API Key 未配置。请通过以下方式之一配置：\n"
                "1. 设置环境变量 OPENAI_API_KEY / DASHSCOPE_API_KEY / DEEPSEEK_API_KEY\n"
                "2. 在 GUI 界面中手动输入\n"
                "3. 创建 .env 文件并添加 API Key"
            )
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self._client: Optional[MockLLMClient] = None

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 16384,
        timeout: int = 300,
    ) -> str:
        """调用 LLM 的 Chat Completion API。

        Args:
            messages: 消息列表，格式为 [{"role": "...", "content": "..."}]
            temperature: 生成温度，0.0-1.0，越低越确定
            max_tokens: 最大生成 token 数
            timeout: 请求超时时间（秒）

        Returns:
            模型生成的文本内容

        Raises:
            RuntimeError: API 调用失败或返回错误
            ImportError: requests 库未安装
        """
        # 模拟模式
        if self._client is not None:
            return self._client.chat(messages, temperature, max_tokens, timeout)
            
        try:
            import requests
        except ImportError:
            raise ImportError(
                "缺少 requests 库，请执行: pip install requests"
            )

        url = f"{self.api_base}/chat/completions"
        # 火山引擎方舟 API 使用 Authorization: Bearer <api_key>
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        logger.info(
            "LLM 请求: model=%s, messages=%d, max_tokens=%d, temp=%.1f",
            self.model, len(messages), max_tokens, temperature,
        )

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.exceptions.Timeout:
            raise RuntimeError(
                f"LLM API 请求超时（{timeout}秒），请检查网络连接或增大超时时间。"
            )
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                f"无法连接到 API 服务器: {self.api_base}\n"
                f"请检查 API Base URL 是否正确以及网络连接。"
            ) from exc

        if resp.status_code != 200:
            error_detail = resp.text[:500]
            raise RuntimeError(
                f"LLM API 返回错误 (HTTP {resp.status_code}): {error_detail}"
            )

        data: dict[str, Any] = resp.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]

        if isinstance(content, str):
            token_usage = data.get("usage", {})
            logger.info(
                "LLM 响应: %d tokens (prompt=%d, completion=%d)",
                token_usage.get("total_tokens", 0),
                token_usage.get("prompt_tokens", 0),
                token_usage.get("completion_tokens", 0),
            )
            return content

        return json.dumps(content, ensure_ascii=False, indent=2)

    def chat_with_system(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 16384,
    ) -> str:
        """简化的带 system prompt 的调用。"""
        return self.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )