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
            model=model or "gpt-5-4",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content
    
    def get_model_name(self, model_id: str) -> str:
        """Map model ID to full name"""
        model_map = {
            "gpt-5-4-pro": "gpt-5-4-pro",
            "gpt-5-4": "gpt-5-4",
            "gpt-5-mini": "gpt-5-mini",
            "gpt-5-nano": "gpt-5-nano"
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
        
        model_name = model or "gemini-3-pro"
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
            "gemini-3-pro": "gemini-3-pro",
            "gemini-3-deep-think": "gemini-3-deep-think",
            "gemini-3-flash": "gemini-3-flash",
            "gemini-3-1-flash-lite": "gemini-3.1-flash-lite",
            "gemini-3-pro-image": "gemini-3-pro-image"
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
            model=model or "grok-4",
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
            model=model or "deepseek-v3-2",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content
    
    def get_model_name(self, model_id: str) -> str:
        return model_id


class ProviderFactory:
    """Factory for creating provider instances"""
    
    PROVIDERS = {
        'anthropic': AnthropicProvider,
        'openai': OpenAIProvider,
        'google': GoogleProvider,
        'xai': XAIProvider,
        'deepseek': DeepSeekProvider,
        'alibaba': DeepSeekProvider,  # Uses OpenAI-compatible API
        'moonshot': DeepSeekProvider,  # Uses OpenAI-compatible API
        'baidu': DeepSeekProvider,  # Uses OpenAI-compatible API
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