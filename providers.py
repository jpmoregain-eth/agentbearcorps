"""
LLM Provider Module
Handles multiple AI providers (Anthropic, OpenAI, Google, etc.)
"""

import os
import logging
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """Base class for LLM providers"""
    
    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key
        self.kwargs = kwargs
    
    @abstractmethod
    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        """Send chat completion request"""
        pass
    
    @abstractmethod
    def get_model_name(self, model_id: str) -> str:
        """Get full model name from ID"""
        pass


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider"""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("anthropic package required. Run: pip install anthropic")
    
    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        """Send message to Claude"""
        # Convert messages to Claude format
        system_msg = None
        user_messages = []
        
        for msg in messages:
            if msg['role'] == 'system':
                system_msg = msg['content']
            else:
                user_messages.append(msg)
        
        # Claude expects alternating user/assistant, so combine consecutive messages
        formatted_messages = []
        for msg in user_messages:
            formatted_messages.append({
                "role": msg['role'],
                "content": msg['content']
            })
        
        kwargs = {
            "model": model or "claude-sonnet-4-6-20251022",
            "max_tokens": max_tokens,
            "messages": formatted_messages
        }
        
        if system_msg:
            kwargs["system"] = system_msg
        
        response = self.client.messages.create(**kwargs)
        return response.content[0].text
    
    def get_model_name(self, model_id: str) -> str:
        """Map model ID to full name"""
        model_map = {
            "claude-opus-4-6": "claude-opus-4-6-20251022",
            "claude-sonnet-4-6": "claude-sonnet-4-6-20251022",
            "claude-haiku-4-5": "claude-haiku-4-5-20241022"
        }
        return model_map.get(model_id, model_id)


class OpenAIProvider(BaseProvider):
    """OpenAI GPT provider"""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        try:
            import openai
            self.client = openai.OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("openai package required. Run: pip install openai")
    
    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        """Send message to GPT"""
        response = self.client.chat.completions.create(
            model=model or "gpt-4o",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content
    
    def get_model_name(self, model_id: str) -> str:
        """Map model ID to full name"""
        model_map = {
            "gpt-4o":        "gpt-4o",
            "gpt-4o-mini":   "gpt-4o-mini",
            "gpt-4-turbo":   "gpt-4-turbo",
            "o1":            "o1",
            "o1-mini":       "o1-mini",
            "o3-mini":       "o3-mini",
        }
        return model_map.get(model_id, model_id)


class GoogleProvider(BaseProvider):
    """Google Gemini provider"""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.genai = genai
        except ImportError:
            raise ImportError("google-generativeai package required. Run: pip install google-generativeai")
    
    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        """Send message to Gemini"""
        # Convert messages to Gemini format
        system_msg = ""
        user_messages = []
        
        for msg in messages:
            if msg['role'] == 'system':
                system_msg = msg['content']
            elif msg['role'] == 'user':
                user_messages.append(msg['content'])
        
        model_name = model or "gemini-1.5-pro"
        gen_model = self.genai.GenerativeModel(model_name)
        
        # Combine user messages
        prompt = "\n\n".join(user_messages)
        if system_msg:
            prompt = f"System: {system_msg}\n\n{prompt}"
        
        response = gen_model.generate_content(prompt)
        return response.text
    
    def get_model_name(self, model_id: str) -> str:
        """Map model ID to full name"""
        model_map = {
            "gemini-1.5-pro":        "gemini-1.5-pro",
            "gemini-1.5-flash":      "gemini-1.5-flash",
            "gemini-2.0-flash":      "gemini-2.0-flash",
            "gemini-2.0-flash-lite": "gemini-2.0-flash-lite",
            "gemini-2.5-pro":        "gemini-2.5-pro-preview-03-25",
        }
        return model_map.get(model_id, model_id)


class XAIProvider(BaseProvider):
    """xAI Grok provider"""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        try:
            import openai
            # xAI uses OpenAI-compatible API
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.x.ai/v1"
            )
        except ImportError:
            raise ImportError("openai package required. Run: pip install openai")
    
    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        """Send message to Grok"""
        response = self.client.chat.completions.create(
            model=model or "grok-2-latest",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content
    
    def get_model_name(self, model_id: str) -> str:
        return model_id


class DeepSeekProvider(BaseProvider):
    """DeepSeek provider"""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        try:
            import openai
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com/v1"
            )
        except ImportError:
            raise ImportError("openai package required. Run: pip install openai")
    
    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        """Send message to DeepSeek"""
        response = self.client.chat.completions.create(
            model=model or "deepseek-chat",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content
    
    def get_model_name(self, model_id: str) -> str:
        return model_id


class AlibabaProvider(BaseProvider):
    """Alibaba Qwen provider (OpenAI-compatible)"""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        try:
            import openai
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        except ImportError:
            raise ImportError("openai package required. Run: pip install openai")

    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        response = self.client.chat.completions.create(
            model=model or "qwen-plus",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content

    def get_model_name(self, model_id: str) -> str:
        return model_id


class MoonshotProvider(BaseProvider):
    """Moonshot Kimi provider (OpenAI-compatible)"""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        try:
            import openai
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.moonshot.cn/v1"
            )
        except ImportError:
            raise ImportError("openai package required. Run: pip install openai")

    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        response = self.client.chat.completions.create(
            model=model or "moonshot-v1-8k",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content

    def get_model_name(self, model_id: str) -> str:
        return model_id


class BaiduProvider(BaseProvider):
    """Baidu ERNIE provider (OpenAI-compatible via Qianfan)"""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        try:
            import openai
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url="https://qianfan.baidubce.com/v2"
            )
        except ImportError:
            raise ImportError("openai package required. Run: pip install openai")

    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        response = self.client.chat.completions.create(
            model=model or "ernie-4.0-8k",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content

    def get_model_name(self, model_id: str) -> str:
        return model_id



    """Local Ollama provider"""
    
    def __init__(self, api_key: str = None, base_url: str = "http://localhost:11434", **kwargs):
        super().__init__(api_key or "ollama", **kwargs)
        self.base_url = base_url
        try:
            import openai
            self.client = openai.OpenAI(
                api_key="ollama",
                base_url=f"{base_url}/v1"
            )
        except ImportError:
            raise ImportError("openai package required. Run: pip install openai")
    
    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        """Send message to local Ollama model"""
        response = self.client.chat.completions.create(
            model=model or "qwen2.5",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content
    
    def get_model_name(self, model_id: str) -> str:
        return model_id


class MockProvider(BaseProvider):
    """Mock provider for testing - returns canned responses"""
    
    def __init__(self, api_key: str = "test", **kwargs):
        super().__init__(api_key, **kwargs)
        self.response_count = 0
    
    def chat(self, messages: List[Dict], model: str = None, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        """Return mock response"""
        self.response_count += 1
        
        # Get the last user message
        last_message = ""
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                last_message = msg.get('content', '')
                break
        
        # Generate contextual mock response
        if "hello" in last_message.lower() or "hi" in last_message.lower():
            return f"🐻 Hello! I'm your test agent (response #{self.response_count}). I received your greeting!"
        elif "?" in last_message:
            return f"🐻 That's an interesting question (response #{self.response_count})! In test mode, I don't have real AI, but the system is working correctly."
        else:
            return f"🐻 I received your message: '{last_message[:50]}...' (response #{self.response_count}). This is a test response - everything is working!"
    
    def get_model_name(self, model_id: str) -> str:
        return model_id or "mock-model"


class ProviderFactory:
    """Factory for creating provider instances"""
    
    PROVIDERS = {
        'anthropic': AnthropicProvider,
        'openai':    OpenAIProvider,
        'google':    GoogleProvider,
        'xai':       XAIProvider,
        'deepseek':  DeepSeekProvider,
        'alibaba':   AlibabaProvider,
        'moonshot':  MoonshotProvider,
        'baidu':     BaiduProvider,
        'ollama':    OllamaProvider,
        'custom':    OllamaProvider,
        'mock':      MockProvider,  # For testing
    }
    
    @classmethod
    def create(cls, provider_name: str, api_key: str, **kwargs) -> BaseProvider:
        """Create a provider instance"""
        provider_class = cls.PROVIDERS.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        return provider_class(api_key, **kwargs)
    
    @classmethod
    def get_provider_for_model(cls, model_id: str) -> Optional[str]:
        """Get provider name for a model ID"""
        # Map model prefixes to providers
        if model_id.startswith('claude'):
            return 'anthropic'
        elif model_id.startswith('gpt'):
            return 'openai'
        elif model_id.startswith('gemini'):
            return 'google'
        elif model_id.startswith('grok'):
            return 'xai'
        elif model_id.startswith('deepseek'):
            return 'deepseek'
        elif model_id.startswith('qwen'):
            return 'alibaba'
        elif model_id.startswith('kimi'):
            return 'moonshot'
        elif model_id.startswith('ernie'):
            return 'baidu'
        return None