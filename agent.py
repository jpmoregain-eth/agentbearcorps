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
        
        # Initialize code tools if capability enabled
        self.code_tools = None
        if any(cap in ['code_generate', 'code_review', 'debug', 'documentation'] 
               for cap in self.config.capabilities.keys()):
            from code_tools import CodeTools
            self.code_tools = CodeTools(self._chat_with_llm)
            logger.info("📝 Code tools initialized")
        
        # Initialize GitHub tools if capability enabled
        self.github_tools = None
        if 'github_integration' in self.config.capabilities:
            from github_tools import GitHubTools
            from crypto_utils import decrypt_value
            
            github_config = self.config.capabilities.get('github_integration', {})
            encrypted_token = github_config.get('api_key', '')
            
            if encrypted_token:
                token = decrypt_value(encrypted_token)
                if token and token != encrypted_token:
                    try:
                        self.github_tools = GitHubTools(token)
                        logger.info("🔗 GitHub integration initialized")
                    except Exception as e:
                        logger.error(f"Failed to initialize GitHub tools: {e}")
                else:
                    logger.error("Failed to decrypt GitHub token")
            else:
                logger.warning("GitHub token not found in config")
        
        # Initialize Crypto tools if capability enabled
        self.crypto_tools = None
        if 'crypto_trading' in self.config.capabilities:
            from crypto_tools import CryptoTools
            from crypto_utils import decrypt_value
            
            crypto_config = self.config.capabilities.get('crypto_trading', {})
            exchange_id = crypto_config.get('exchange', 'binance')
            encrypted_key = crypto_config.get('api_key', '')
            encrypted_secret = crypto_config.get('api_secret', '')
            
            # Decrypt if provided, otherwise use empty strings (public data only)
            api_key = decrypt_value(encrypted_key) if encrypted_key else ''
            api_secret = decrypt_value(encrypted_secret) if encrypted_secret else ''
            
            try:
                self.crypto_tools = CryptoTools(
                    exchange_id=exchange_id,
                    api_key=api_key,
                    api_secret=api_secret
                )
                logger.info(f"💰 Crypto tools initialized for {exchange_id}")
            except Exception as e:
                logger.error(f"Failed to initialize crypto tools: {e}")
        
        # Initialize Web Search tools if capability enabled
        self.web_search_tools = None
        if 'web_search' in self.config.capabilities:
            from web_search_tools import WebSearchTools
            
            try:
                self.web_search_tools = WebSearchTools()
                logger.info("🔍 Web search tools initialized")
            except Exception as e:
                logger.error(f"Failed to initialize web search tools: {e}")
        
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
        
        # Skip if message contains code blocks (likely code review/debug)
        if '```' in message or '`' in message:
            return None
        
        # Skip if looks like code (contains common code patterns)
        code_indicators = ['def ', 'class ', 'import ', 'print(', 'input(', '= ', 'return ', 'if ', 'for ', 'while ']
        if any(indicator in message for indicator in code_indicators):
            return None
        
        # File read: MUST start with read/show/cat/display
        read_patterns = [
            r'^(?:read|show|cat|display)\s+(?:file\s+)?["\']?((?:~\/|\/|\.)[^"\']+)["\']?$',
            r'^(?:open|view)\s+(?:file\s+)?["\']?((?:~\/|\/|\.)[^"\']+)["\']?$',
        ]
        for pattern in read_patterns:
            match = re.search(pattern, msg_lower)
            if match:
                file_path = match.group(1).strip()
                return self.file_tools.read_file(file_path)
        
        # Directory list: explicit commands only
        if msg_lower.startswith(('list files', 'ls', 'show files', 'list directory')):
            # Extract directory path if specified (must look like a path)
            dir_match = re.search(r'(?:in|from)\s+((?:~\/|\/|\.)[^\s]+)', msg_lower)
            dir_path = dir_match.group(1) if dir_match else "."
            return self.file_tools.list_directory(dir_path)
        
        # File write: "write X to file Y" - Y must look like a path
        write_match = re.search(r'^(?:write|save)\s+["\']?(.+?)["\']?\s+to\s+(?:file\s+)?["\']?((?:~\/|\/|\.)[^"\']+)["\']?$', msg_lower)
        if write_match:
            content = write_match.group(1)
            file_path = write_match.group(2)
            return self.file_tools.write_file(file_path, content)
        
        # File edit: "change X to Y in file Z" - Z must look like a path
        edit_match = re.search(r'^(?:change|replace|edit)\s+["\']?(.+?)["\']?\s+to\s+["\']?(.+?)["\']?\s+in\s+(?:file\s+)?["\']?((?:~\/|\/|\.)[^"\']+)["\']?$', msg_lower)
        if edit_match:
            old_text = edit_match.group(1)
            new_text = edit_match.group(2)
            file_path = edit_match.group(3)
            return self.file_tools.edit_file(file_path, old_text, new_text)
        
        return None
    
    def _chat_with_llm(self, prompt: str, session_id: str = None) -> Dict:
        """
        Helper method for tools to chat with LLM
        
        Args:
            prompt: The prompt to send
            session_id: Optional session ID
            
        Returns:
            Dict with response
        """
        if not session_id:
            session_id = f"tool_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Get provider
        provider = self._get_provider_for_model(self.config.primary_model)
        if not provider:
            return {'response': 'Error: No LLM provider available'}
        
        # Build messages
        messages = [
            {'role': 'system', 'content': self._get_system_prompt()},
            {'role': 'user', 'content': prompt}
        ]
        
        try:
            response_text = provider.chat(
                messages=messages,
                model=self.config.primary_model,
                max_tokens=4000,
                temperature=0.3
            )
            return {'response': response_text}
        except Exception as e:
            logger.error(f"LLM chat failed: {e}")
            return {'response': f'Error: {str(e)}'}
    
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
        
        # IMPORTANT: Check code commands BEFORE file commands
        # so code review/debug takes priority over file operations
        # (prevents "in" inside code from triggering file commands)
        
        # Check for code commands (if code tools enabled)
        if self.code_tools:
            code_result = self.code_tools.detect_and_execute(message)
            if code_result:
                # Format code result as response
                if code_result.get('success'):
                    if 'code' in code_result:
                        response = f"📝 **Generated {code_result.get('language', 'code').title()} Code:**\n\n{code_result['code']}"
                    elif 'review' in code_result:
                        response = f"🔍 **Code Review:**\n\n{code_result['review']}"
                    elif 'analysis' in code_result:
                        response = f"🐛 **Debug Analysis:**\n\n{code_result['analysis']}"
                    elif 'documented_code' in code_result:
                        response = f"📚 **Documented Code:**\n\n{code_result['documented_code']}"
                    else:
                        response = f"✅ {code_result}"
                else:
                    response = f"❌ Error: {code_result.get('error', 'Unknown error')}"
                
                return {
                    'response': response,
                    'session_id': session_id,
                    'tool_result': code_result
                }
        
        # Check for GitHub commands (if GitHub tools enabled)
        if self.github_tools:
            github_result = self.github_tools.detect_and_execute(message)
            if github_result:
                # Format GitHub result as response
                if github_result.get('success'):
                    if 'content' in github_result:  # File content
                        content_preview = github_result['content'][:500] + "..." if len(github_result['content']) > 500 else github_result['content']
                        response = f"📄 **{github_result.get('path')}** from [{github_result.get('repo', 'repo')}]({github_result.get('url')}):\n```\n{content_preview}\n```"
                    elif 'issues' in github_result:
                        issues_text = '\n'.join([f"#{i['number']}: {i['title']} ({i['state']})" for i in github_result['issues'][:5]])
                        response = f"🐛 **Issues in {github_result.get('repo')}** ({github_result.get('count')} total):\n\n{issues_text}"
                    elif 'items' in github_result:  # Directory listing
                        items_text = '\n'.join([f"{'📁' if i['type'] == 'dir' else '📄'} {i['name']}" for i in github_result['items']])
                        response = f"📁 **{github_result.get('repo')}:{github_result.get('path') or '/'}**\n\n{items_text}"
                    elif 'full_name' in github_result:  # Repo info
                        response = f"📊 **{github_result.get('full_name')}**\n⭐ {github_result.get('stars')} stars | 🍴 {github_result.get('forks')} forks | 🐛 {github_result.get('open_issues')} open issues\n\n{github_result.get('description', 'No description')}"
                    else:
                        response = f"✅ GitHub operation successful: {github_result}"
                else:
                    response = f"❌ GitHub Error: {github_result.get('error', 'Unknown error')}"
                
                return {
                    'response': response,
                    'session_id': session_id,
                    'tool_result': github_result
                }
        
        # Check for Crypto commands (if crypto tools enabled)
        if self.crypto_tools:
            crypto_result = self.crypto_tools.detect_and_execute(message)
            if crypto_result:
                # Format crypto result as response
                if crypto_result.get('success'):
                    if 'price' in crypto_result:  # Ticker
                        response = f"💰 **{crypto_result.get('symbol')}** on {crypto_result.get('exchange')}\n"
                        response += f"Price: ${crypto_result.get('price'):,.2f}\n"
                        response += f"24h Change: {crypto_result.get('change_percent_24h', 0):+.2f}%\n"
                        response += f"24h High: ${crypto_result.get('high_24h', 0):,.2f} | Low: ${crypto_result.get('low_24h', 0):,.2f}\n"
                        response += f"Volume: {crypto_result.get('volume_24h', 0):,.2f}"
                    elif 'candles' in crypto_result:  # OHLCV
                        response = f"📊 **{crypto_result.get('symbol')}** {crypto_result.get('timeframe')} candles ({crypto_result.get('count')}):\n```\n"
                        for c in crypto_result['candles'][-5:]:  # Show last 5
                            response += f"O: {c['open']:,.2f} H: {c['high']:,.2f} L: {c['low']:,.2f} C: {c['close']:,.2f}\n"
                        response += "```"
                    elif 'balances' in crypto_result:  # Balance
                        balance_text = '\n'.join([f"{k}: {v}" for k, v in list(crypto_result['balances'].items())[:10]])
                        response = f"💼 **Balance on {crypto_result.get('exchange')}** ({crypto_result.get('total_currencies')} currencies):\n```\n{balance_text}\n```"
                    elif 'symbols' in crypto_result:  # Symbols list
                        symbols_text = ', '.join(crypto_result['symbols'][:20])
                        response = f"📈 **{crypto_result.get('total')} pairs available** with {crypto_result.get('quote_currency')}\n{symbols_text}..."
                    else:
                        response = f"✅ Crypto operation successful"
                else:
                    response = f"❌ Crypto Error: {crypto_result.get('error', 'Unknown error')}"
                
                return {
                    'response': response,
                    'session_id': session_id,
                    'tool_result': crypto_result
                }
        
        # Check for Web Search commands (if web search tools enabled)
        if self.web_search_tools:
            web_result = self.web_search_tools.detect_and_execute(message)
            if web_result:
                # Format web result as response
                if web_result.get('success'):
                    if 'results' in web_result:  # Search results
                        results_text = '\n\n'.join([
                            f"**{i+1}. {r['title']}**\n{r['snippet'][:150]}...\n🔗 {r['url']}"
                            for i, r in enumerate(web_result['results'])
                        ])
                        response = f"🔍 **Web Search: '{web_result.get('query')}'** ({web_result.get('count')} results):\n\n{results_text}"
                    elif 'content' in web_result:  # Page fetch
                        content_preview = web_result['content'][:800] + "..." if len(web_result['content']) > 800 else web_result['content']
                        response = f"📄 **Fetched: {web_result.get('url')}**\n\n{content_preview}"
                    else:
                        response = f"✅ Web operation successful"
                else:
                    response = f"❌ Web Error: {web_result.get('error', 'Unknown error')}"
                
                return {
                    'response': response,
                    'session_id': session_id,
                    'tool_result': web_result
                }
        
        # Check for file commands (if file tools enabled)
        # Note: Must come AFTER code tools to avoid matching "in" inside code
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
        
        # Get conversation history for LLM chat
        history = []
        if self.memory:
            history = self.memory.get_conversation_history(session_id, limit=20)
        
        # Build messages for LLM
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