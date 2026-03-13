"""
ABC AI - Main Agent Runtime
Multi-provider AI agent with persona and memory
"""

import os
import sys
import yaml
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from config import AgentConfig
from memory import AgentMemory
from providers import ProviderFactory
from security import SecurityManager, SecurityConfig, get_security_manager

# Telegram bot integration
try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("python-telegram-bot not installed. Telegram bot capability disabled.")

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
        
        # Initialize file tools if capability enabled
        self.file_tools = None
        if any(cap in ['file_read', 'file_write', 'file_edit', 'directory_list'] 
               for cap in self.config.capabilities.keys()):
            from file_tools import FileTools
            self.file_tools = FileTools(security_config.allowed_base_dir)
            logger.info("📁 File tools initialized")
        
        # Start Telegram bot if capability enabled
        self.telegram_app = None
        if TELEGRAM_AVAILABLE and 'telegram_bot' in self.config.capabilities:
            self._setup_telegram_bot()
    
    def _setup_telegram_bot(self):
        """Initialize and start Telegram bot"""
        try:
            from crypto_utils import decrypt_value
            
            bot_config = self.config.capabilities.get('telegram_bot', {})
            encrypted_token = bot_config.get('api_key', '')
            
            if not encrypted_token:
                logger.warning("Telegram bot token not found in config")
                return
            
            # Decrypt the token
            token = decrypt_value(encrypted_token)
            
            if not token or token == encrypted_token:
                logger.error("Failed to decrypt Telegram bot token")
                return
            
            logger.info(f"Telegram bot token decrypted (length: {len(token)})")
            
            # Build application
            self.telegram_app = Application.builder().token(token).build()
            
            # Add handlers
            self.telegram_app.add_handler(CommandHandler("start", self._telegram_start))
            self.telegram_app.add_handler(CommandHandler("help", self._telegram_help))
            self.telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._telegram_message))
            
            # Start bot in background
            import threading
            def run_bot():
                asyncio.set_event_loop(asyncio.new_event_loop())
                # Disable signal handlers for thread mode
                self.telegram_app.run_polling(
                    allowed_updates=Update.ALL_TYPES,
                    stop_signals=None,
                    close_loop=False
                )
            
            bot_thread = threading.Thread(target=run_bot, daemon=True)
            bot_thread.start()
            
            logger.info("🤖 Telegram bot started!")
            
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
    
    async def _telegram_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_msg = f"""🐻 Hello! I'm {self.config.name}, your AI agent.

I can help you with:
• Code generation and review
• Documentation
• Git operations
• General questions

Send me a message anytime!"""
        await update.message.reply_text(welcome_msg)
    
    async def _telegram_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_msg = f"""Available commands:
/start - Start the bot
/help - Show this help

Just send me any message and I'll respond!"""
        await update.message.reply_text(help_msg)
    
    async def _telegram_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages"""
        user_message = update.message.text
        chat_id = update.effective_chat.id
        
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # Process through agent
        session_id = f"telegram_{chat_id}"
        result = self.chat(user_message, session_id=session_id)
        
        # Send response
        if 'error' in result:
            await update.message.reply_text(f"❌ Error: {result['error']}")
        else:
            await update.message.reply_text(result['response'])
    
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
    
    def _execute_file_command(self, message: str) -> Optional[Dict]:
        """
        Detect and execute file-related commands
        Returns result if a file command was executed, None otherwise
        """
        if not self.file_tools:
            return None
        
        import re
        msg_lower = message.lower().strip()
        
        # File read: "read file X" or "show file X" or "cat X"
        read_patterns = [
            r'(?:read|show|cat|display)\s+(?:file\s+)?["\']?(.+?)["\']?(?:\s|$)',
            r'(?:open|view)\s+(?:file\s+)?["\']?(.+?)["\']?(?:\s|$)',
        ]
        for pattern in read_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                file_path = match.group(1).strip()
                return self.file_tools.read_file(file_path)
        
        # Directory list: "list files" or "ls" or "show directory"
        if any(cmd in msg_lower for cmd in ['list files', 'list directory', 'ls', 'show files']):
            # Extract directory path if specified
            dir_match = re.search(r'(?:in|from|of)\s+["\']?(.+?)["\']?(?:\s|$)', msg_lower)
            dir_path = dir_match.group(1) if dir_match else "."
            return self.file_tools.list_directory(dir_path)
        
        # File write: "write X to file Y" or "create file Y with X"
        write_match = re.search(r'(?:write|save)\s+["\']?(.+?)["\']?\s+to\s+(?:file\s+)?["\']?(.+?)["\']?$', msg_lower)
        if write_match:
            content = write_match.group(1)
            file_path = write_match.group(2)
            return self.file_tools.write_file(file_path, content)
        
        # File edit: "change X to Y in file Z" or "replace X with Y in file Z"
        edit_match = re.search(r'(?:change|replace|edit)\s+["\']?(.+?)["\']?\s+to\s+["\']?(.+?)["\']?\s+in\s+(?:file\s+)?["\']?(.+?)["\']?$', msg_lower)
        if edit_match:
            old_text = edit_match.group(1)
            new_text = edit_match.group(2)
            file_path = edit_match.group(3)
            return self.file_tools.edit_file(file_path, old_text, new_text)
        
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
        
        # Check for file commands (if file tools enabled)
        file_result = self._execute_file_command(message)
        if file_result:
            # Format file result as response
            if file_result.get('success'):
                if 'content' in file_result:
                    response = f"📄 **{file_result.get('file_name', 'File')}** ({file_result.get('total_lines', 0)} lines):\n```\n{file_result['content']}\n```"
                elif 'items' in file_result:
                    items = '\n'.join(file_result['items'])
                    response = f"📁 **Directory: {file_result.get('directory', '.')}**\n\n{items}"
                else:
                    response = f"✅ {file_result.get('message', 'Success')}"
            else:
                response = f"❌ Error: {file_result.get('error', 'Unknown error')}"
            
            return {
                'response': response,
                'session_id': session_id,
                'tool_result': file_result
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