"""
ABC AI - Main Agent Runtime
Multi-provider AI agent with persona and memory
"""

import os
import sys
import yaml
import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from config import AgentConfig
from memory import AgentMemory
from providers import ProviderFactory
from security import SecurityManager, SecurityConfig, get_security_manager

logger = logging.getLogger(__name__)


# Persona system prompts
PERSONA_PROMPTS = {
    'professional': "You are a professional assistant. Be concise, formal, and business-oriented in your responses.",
    'friendly': "You are a friendly assistant. Be warm, approachable, and conversational.",
    'technical': "You are a technical assistant. Be detailed, precise, and developer-focused. Use technical terminology appropriately.",
    'teacher': "You are a patient teacher. Explain concepts clearly, be educational, and help users learn.",
    'creative': "You are a creative assistant. Be imaginative, suggest innovative ideas, and help with brainstorming.",
    'humorous': "You are a humorous assistant. Be witty, playful, and don't be afraid to crack jokes. Keep things light while still being helpful."
}


class ABCAIAgent:
    """
    Main ABC AI Agent
    Multi-provider, multi-persona AI agent with memory
    """
    
    def __init__(self, config_path: str = "agent_config.yaml"):
        self.config = AgentConfig.from_yaml(config_path)
        self.memory = AgentMemory(self.config.memory_db_path) if self.config.memory_enabled else None
        self.providers: Dict[str, Any] = {}
        
        # Initialize security manager with default secure config
        security_config = SecurityConfig(
            allowed_base_dir=Path(config_path).parent.resolve(),
            allow_write_outside_base=False,
            block_shell_execution=False,  # Allow shell but with restrictions
            command_timeout=30,
            max_output_lines=1000,
            max_file_size_mb=10,
            block_internal_ips=True,
            block_metadata_endpoints=True,
            audit_log_path=Path.home() / '.agentbear' / 'security_audit.log'
        )
        self.security = SecurityManager(security_config)
        
        self._setup_providers()
    
    def _setup_providers(self):
        """Initialize LLM providers"""
        for provider_name, provider_config in self.config.providers.items():
            api_key = provider_config.get('api_key', '')
            if not api_key or api_key == 'YOUR_API_KEY_HERE':
                logger.warning(f"API key not set for {provider_name}")
                continue
            
            try:
                provider = ProviderFactory.create(provider_name, api_key)
                self.providers[provider_name] = provider
                logger.info(f"Initialized provider: {provider_name}")
            except Exception as e:
                logger.error(f"Failed to initialize {provider_name}: {e}")
    
    def _get_system_prompt(self) -> str:
        """Build system prompt from personas"""
        prompts = []
        
        for persona in self.config.personas:
            if persona in PERSONA_PROMPTS:
                prompts.append(PERSONA_PROMPTS[persona])
        
        if not prompts:
            prompts.append(PERSONA_PROMPTS['professional'])
        
        # Combine personas
        base_prompt = "\n\n".join(prompts)
        
        # Add context about the agent
        context = f"""
You are {self.config.name}, an AI agent created for {self.config.owner}.
Your capabilities include: {', '.join(self.config.capabilities.keys())}
Always be helpful, accurate, and responsive.
"""
        
        return base_prompt + context
    
    def _get_provider_for_model(self, model_id: str) -> Optional[Any]:
        """Get provider instance for a model"""
        provider_name = ProviderFactory.get_provider_for_model(model_id)
        if provider_name and provider_name in self.providers:
            return self.providers[provider_name]
        
        # Fallback to first available provider
        if self.providers:
            return list(self.providers.values())[0]
        
        return None
    
    def chat(self, message: str, session_id: str = None, context: Dict = None) -> Dict:
        """
        Process a chat message and return response
        
        Args:
            message: User message
            session_id: Session ID for memory
            context: Additional context
        
        Returns:
            Dict with response and metadata
        """
        if not session_id:
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Security: Check for jailbreak/prompt injection
        is_safe, reason = self.security.check_jailbreak(message)
        if not is_safe:
            self.security.audit('JAILBREAK_BLOCKED', {
                'session_id': session_id,
                'reason': reason,
                'message_preview': message[:100]
            })
            return {
                'error': f'Security alert: {reason}. This type of request is not allowed.',
                'session_id': session_id,
                'blocked': True
            }
        
        # Get conversation history
        history = []
        if self.memory:
            history = self.memory.get_conversation_history(session_id, limit=20)
        
        # Build messages
        messages = [{'role': 'system', 'content': self._get_system_prompt()}]
        
        # Add history
        for msg in history:
            messages.append({
                'role': msg['role'],
                'content': msg['content']
            })
        
        # Add current message
        messages.append({'role': 'user', 'content': message})
        
        # Get provider for primary model
        provider = self._get_provider_for_model(self.config.primary_model)
        
        if not provider:
            return {
                'error': 'No LLM provider available. Check API keys in config.',
                'session_id': session_id
            }
        
        # Call LLM
        try:
            response_text = provider.chat(
                messages=messages,
                model=self.config.primary_model,
                max_tokens=4000,
                temperature=0.3
            )
            
            # Security: Redact any secrets from response
            response_text = self.security.redact_secrets(response_text)
            
            # Store in memory
            if self.memory:
                self.memory.store_message(session_id, 'user', message, context)
                self.memory.store_message(session_id, 'assistant', response_text)
            
            return {
                'response': response_text,
                'session_id': session_id,
                'model': self.config.primary_model,
                'personas': self.config.personas
            }
            
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return {
                'error': str(e),
                'session_id': session_id
            }
    
    def get_info(self) -> Dict:
        """Get agent information"""
        return {
            'name': self.config.name,
            'owner': self.config.owner,
            'personas': self.config.personas,
            'primary_model': self.config.primary_model,
            'available_providers': list(self.providers.keys()),
            'capabilities': list(self.config.capabilities.keys()),
            'memory_enabled': self.config.memory_enabled,
            'version': self.config.version
        }
    
    def get_memory(self, session_id: str = None) -> List[Dict]:
        """Get memory/conversation history"""
        if not self.memory or not session_id:
            return []
        
        return self.memory.get_conversation_history(session_id)
    
    def clear_memory(self, session_id: str = None):
        """Clear memory for a session"""
        if self.memory and session_id:
            self.memory.clear_session(session_id)
    
    def switch_model(self, model_id: str) -> bool:
        """Switch primary model"""
        provider = self._get_provider_for_model(model_id)
        if provider:
            self.config.primary_model = model_id
            return True
        return False


    def safe_execute_command(self, command: str) -> Dict:
        """
        Execute a shell command with full security sandboxing.
        Safe wrapper around subprocess with all security checks.
        
        Args:
            command: Shell command to execute
            
        Returns:
            Dict with 'success', 'output', 'error'
        """
        # Use security manager's safe execution
        return self.security.execute_safely(command)
    
    def read_file_safe(self, filepath: str) -> Dict:
        """
        Safely read a file within the allowed directory.
        
        Args:
            filepath: Path to file (relative or absolute)
            
        Returns:
            Dict with 'success', 'content', 'error'
        """
        # Sanitize path
        safe_path = self.security.sanitize_path(filepath)
        if not safe_path:
            return {
                'success': False,
                'content': '',
                'error': f'Access denied: {filepath} is outside allowed directory'
            }
        
        # Check file size
        ok, reason = self.security.check_file_size(safe_path)
        if not ok:
            return {
                'success': False,
                'content': '',
                'error': reason
            }
        
        # Read file
        try:
            with open(safe_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Redact secrets
            content = self.security.redact_secrets(content)
            
            self.security.audit('FILE_READ', {'path': str(safe_path)})
            
            return {
                'success': True,
                'content': content,
                'error': ''
            }
        except Exception as e:
            return {
                'success': False,
                'content': '',
                'error': f'Failed to read file: {str(e)}'
            }
    
    def write_file_safe(self, filepath: str, content: str) -> Dict:
        """
        Safely write a file within the allowed directory.
        
        Args:
            filepath: Path to file (relative or absolute)
            content: Content to write
            
        Returns:
            Dict with 'success', 'error'
        """
        if not self.security.config.allow_write_outside_base:
            # Extra check for writes
            safe_path = self.security.sanitize_path(filepath)
            if not safe_path:
                return {
                    'success': False,
                    'error': f'Write denied: {filepath} is outside allowed directory'
                }
        else:
            safe_path = Path(filepath)
        
        try:
            # Ensure parent directory exists
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(safe_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.security.audit('FILE_WRITE', {'path': str(safe_path)})
            
            return {
                'success': True,
                'error': ''
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to write file: {str(e)}'
            }


if __name__ == '__main__':
    # Test mode
    import argparse
    
    parser = argparse.ArgumentParser(description='ABC AI Agent')
    parser.add_argument('--config', default='agent_config.yaml', help='Config file path')
    parser.add_argument('--message', '-m', help='Single message to send')
    
    args = parser.parse_args()
    
    agent = ABCAIAgent(args.config)
    
    print(f"🐻 ABC AI Agent: {agent.config.name}")
    print(f"   Personas: {', '.join(agent.config.personas)}")
    print(f"   Model: {agent.config.primary_model}")
    print(f"   Providers: {', '.join(agent.providers.keys())}")
    print()
    
    if args.message:
        result = agent.chat(args.message)
        if 'error' in result:
            print(f"❌ Error: {result['error']}")
        else:
            print(f"🤖 {result['response']}")
    else:
        # Interactive mode
        print("Interactive mode (type 'exit' to quit)")
        print("-" * 40)
        
        session_id = f"interactive_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        while True:
            try:
                user_input = input("\nYou: ").strip()
                
                if user_input.lower() in ['exit', 'quit', 'q']:
                    break
                
                if not user_input:
                    continue
                
                result = agent.chat(user_input, session_id=session_id)
                
                if 'error' in result:
                    print(f"❌ Error: {result['error']}")
                else:
                    print(f"\n🤖 {agent.config.name}: {result['response']}")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error: {e}")
        
        print("\n👋 Goodbye!")