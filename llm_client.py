#!/usr/bin/env python3
"""
LLM 统一调用接口
================
支持 Anthropic 协议 (LongCat 等) 和 OpenAI 协议 (DeepSeek / 通义 / 智谱 / Moonshot / OpenAI 等)。
供 pigai_auto.py 调用，屏蔽不同厂商 SDK 的差异。
"""

# ----------------------------------------------------------
# 预设供应商映射 (供 server.py 和前端共用)
# ----------------------------------------------------------
PROVIDER_PRESETS = {
    "longcat": {
        "name": "LongCat (闪极星)",
        "protocol": "anthropic",
        "base_url": "https://api.longcat.chat/anthropic",
        "model": "LongCat-2.0",
    },
    "deepseek": {
        "name": "DeepSeek (深度求索)",
        "protocol": "openai",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "qwen": {
        "name": "通义千问 (Qwen)",
        "protocol": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "glm": {
        "name": "智谱 GLM",
        "protocol": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-plus",
    },
    "moonshot": {
        "name": "Moonshot (月之暗面)",
        "protocol": "openai",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "openai": {
        "name": "OpenAI",
        "protocol": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
    },
    "custom": {
        "name": "自定义",
        "protocol": "anthropic",
        "base_url": "",
        "model": "",
    },
}


class LLMError(Exception):
    """LLM 调用异常 (空 key / 空响应 / SDK 报错等)"""
    pass


class LLMClient:
    """统一 LLM 调用接口，根据 protocol 选择对应 SDK。"""

    def __init__(self, api_config: dict):
        api_config = api_config or {}
        self.protocol = api_config.get("protocol", "anthropic")
        self.api_key = api_config.get("key", "")
        self.base_url = api_config.get("base_url", "")
        self.model = api_config.get("model", "")
        self.max_tokens = api_config.get("max_tokens", 8000)

    def generate(self, prompt: str) -> str:
        """
        调用 LLM 生成文本。
        成功返回文本字符串；失败抛 LLMError，由调用方 fallback 到模板。
        """
        if not self.api_key:
            raise LLMError("未配置 API Key")

        if self.protocol == "openai":
            return self._generate_openai(prompt)
        return self._generate_anthropic(prompt)

    # ----------------------------------------------------------
    # Anthropic 协议
    # ----------------------------------------------------------
    def _generate_anthropic(self, prompt: str) -> str:
        try:
            import anthropic
        except ImportError:
            raise LLMError("未安装 anthropic SDK，请运行: pip install anthropic")

        try:
            client = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            message = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            # 提取文本块 (跳过 ThinkingBlock)
            for block in message.content:
                if hasattr(block, "text"):
                    text = block.text.strip()
                    if text:
                        return text
            raise LLMError("API 返回中未找到文本内容")
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Anthropic API 调用失败: {e}")

    # ----------------------------------------------------------
    # OpenAI 协议
    # ----------------------------------------------------------
    def _generate_openai(self, prompt: str) -> str:
        try:
            import openai
        except ImportError:
            raise LLMError("未安装 openai SDK，请运行: pip install openai")

        try:
            client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

            kwargs = dict(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            if self.max_tokens:
                kwargs["max_tokens"] = self.max_tokens

            # 部分新模型不接受 max_tokens，失败时去掉重试一次
            try:
                resp = client.chat.completions.create(**kwargs)
            except Exception as first_err:
                if "max_tokens" in kwargs:
                    kwargs.pop("max_tokens", None)
                    resp = client.chat.completions.create(**kwargs)
                else:
                    raise first_err

            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise LLMError("API 返回内容为空")
            return text
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"OpenAI API 调用失败: {e}")
