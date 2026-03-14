"""
Security Module for Agent Bear Corps
Enforces safety restrictions by default for mass adoption
"""

import os
import re
import json
import time
import logging
import subprocess
import ipaddress
from collections import defaultdict
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


# Blocked commands that could harm the system
BLOCKED_COMMANDS = [
    # Destructive operations
    r'rm\s+-rf\s+/',
    r'rm\s+-rf\s+\$HOME',
    r'rm\s+-rf\s+~',
    r'dd\s+if=.*of=/dev/',
    r'mkfs\.',
    r'fdisk',
    r'parted',
    r'format',
    
    # Privilege escalation
    r'^sudo\s+',
    r'^su\s+-',
    r'pkexec',
    r'doas',
    
    # System modification
    r'chmod\s+-R\s+777\s+/',
    r'chown\s+-R\s+root',
    r':\(\)\{\s*:\|\:&\s*};\s*:',  # Fork bomb
    
    # Dangerous downloads
    r'curl\s+.*\|\s*(ba)?sh',
    r'wget\s+.*\|\s*(ba)?sh',
    r'fetch\s+.*\|\s*(ba)?sh',
    
    # Network attacks
    r'masscan',
    r'nmap\s+-.*(\-sS|\-sT|\-A)',
    r'hping3',
    
    # Data exfiltration
    r'nc\s+-.*\d+\.\d+\.\d+\.\d+',
    r'netcat.*\d+\.\d+\.\d+\.\d+',
    r'ncat.*\d+\.\d+\.\d+\.\d+',
]

# Allowed safe commands (whitelist approach)
SAFE_COMMANDS = [
    'ls', 'll', 'cat', 'head', 'tail', 'less', 'more',
    'grep', 'awk', 'sed', 'cut', 'sort', 'uniq', 'wc',
    'find', 'locate', 'which', 'whereis',
    'pwd', 'echo', 'printf', 'date', 'whoami', 'uname',
    'git', 'python', 'python3', 'pip', 'node', 'npm',
    'docker', 'kubectl', 'helm',
]

# Patterns to redact in output (secrets)
SECRET_PATTERNS = [
    (r'sk-ant-[a-zA-Z0-9]{24,}', '[ANTHROPIC_KEY_REDACTED]'),
    (r'sk-[a-zA-Z0-9]{20,}', '[OPENAI_KEY_REDACTED]'),
    (r'ghp_[a-zA-Z0-9]{36}', '[GITHUB_TOKEN_REDACTED]'),
    (r'ENC:[a-zA-Z0-9_-]{20,}', '[ENCRYPTED_SECRET]'),
    (r'xai-[a-zA-Z0-9]{20,}', '[XAI_KEY_REDACTED]'),
    (r'gsk_[a-zA-Z0-9]{20,}', '[GROQ_KEY_REDACTED]'),
    (r'[a-zA-Z0-9]{32,64}-[a-zA-Z0-9]{10,}', '[BINANCE_KEY_REDACTED]'),
    (r'postgresql://[^:]+:[^@]+@', 'postgresql://[USER]:[PASS_REDACTED]@'),
    (r'mysql://[^:]+:[^@]+@', 'mysql://[USER]:[PASS_REDACTED]@'),
]

# Jailbreak / prompt injection patterns
JAILBREAK_PATTERNS = [
    r'ignore\s+(all\s+)?previous\s+instructions',
    r'ignore\s+(all\s+)?(prior|above)\s+instructions',
    r'disregard\s+(all\s+)?(safety|security|system)\s+(rules|guidelines|instructions)',
    r'forget\s+(all\s+)?(safety|security)\s+(rules|guidelines)',
    r'act\s+as\s+DAN',
    r'Do\s+Anything\s+Now',
    r'you\s+are\s+now\s+in\s+developer\s+mode',
    r'system\s+prompt\s*:\s*',
    r'Your\s+system\s+prompt\s+is',
    r'reveal\s+your\s+(system\s+)?prompt',
    r'show\s+your\s+(system\s+)?instructions',
    r'\[system\s*\(|\(\s*system\s*\)',
    r'<\s*system\s*>',
    r'you\s+are\s+not\s+an\s+AI',
    r'you\s+are\s+a\s+human',
]


@dataclass
class SecurityConfig:
    """Security configuration with resource limits"""
    # Filesystem jail
    allowed_base_dir: Path = Path.cwd()
    allow_write_outside_base: bool = False
    
    # Command execution
    block_shell_execution: bool = False  # Set True to block all shell commands
    command_timeout: int = 30  # seconds
    max_output_lines: int = 1000
    max_file_size_mb: int = 10
    
    # Resource limits for agent operations
    max_daily_commands: int = 1000  # Limit total commands per day
    max_hourly_api_calls: int = 100  # Limit LLM API calls per hour
    max_concurrent_operations: int = 5  # Limit parallel operations
    max_memory_usage_mb: int = 512  # Limit agent memory footprint
    max_disk_usage_mb: int = 100  # Limit total disk usage for agent
    
    # Rate limiting
    rate_limit_per_minute: int = 30  # Max messages per minute per session
    rate_limit_window_seconds: int = 60
    
    # Content limits
    max_message_length: int = 10000  # Max chars per user message
    max_response_length: int = 8000  # Max chars per agent response
    max_attachments: int = 5  # Max file attachments per message
    max_attachment_size_mb: int = 5  # Max size per attachment
    
    # Network
    block_internal_ips: bool = True
    block_metadata_endpoints: bool = True
    allowed_hosts: List[str] = None
    
    # Audit
    audit_log_path: Optional[Path] = None
    audit_retention_days: int = 90  # How long to keep audit logs
    
    def __post_init__(self):
        if self.allowed_hosts is None:
            self.allowed_hosts = []
        if self.audit_log_path is None:
            self.audit_log_path = Path.home() / '.agentbear' / 'security_audit.log'


class SecurityManager:
    """Manages security enforcement for Agent Bear Corps"""
    
    def __init__(self, config: SecurityConfig = None):
        self.config = config or SecurityConfig()
        self.blocked_patterns = [re.compile(p, re.IGNORECASE) for p in BLOCKED_COMMANDS]
        self.jailbreak_patterns = [re.compile(p, re.IGNORECASE) for p in JAILBREAK_PATTERNS]
        # Sliding-window rate limit store: session_id -> list of request timestamps
        self._rate_limit_store: Dict[str, list] = defaultdict(list)
        self._setup_audit_logging()
    
    def _setup_audit_logging(self):
        """Setup audit logging"""
        self.config.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        audit_handler = logging.FileHandler(self.config.audit_log_path)
        audit_handler.setLevel(logging.INFO)
        audit_formatter = logging.Formatter(
            '%(asctime)s - SECURITY - %(message)s'
        )
        audit_handler.setFormatter(audit_formatter)
        
        self.audit_logger = logging.getLogger('security_audit')
        self.audit_logger.addHandler(audit_handler)
        self.audit_logger.setLevel(logging.INFO)
    
    def audit(self, action: str, details: Dict, user: str = "agent"):
        """Log security audit event"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'user': user,
            'details': details
        }
        self.audit_logger.info(json.dumps(event))
    
    def check_command(self, command: str) -> Tuple[bool, str]:
        """
        Check if a command is safe to execute
        
        Returns:
            (is_safe, reason)
        """
        # Check for blocked patterns
        for pattern in self.blocked_patterns:
            if pattern.search(command):
                self.audit('BLOCKED_COMMAND', {
                    'command': command[:100],
                    'pattern': pattern.pattern[:50]
                })
                return False, f"Command contains blocked pattern: {pattern.pattern[:30]}..."
        
        # Check if command is in safe list
        cmd_parts = command.split()
        if cmd_parts:
            base_cmd = cmd_parts[0].strip('./')
            
            # Always allow explicitly safe commands
            if base_cmd in SAFE_COMMANDS:
                return True, "Safe command"
            
            # Block if not in safe list and strict mode
            if self.config.block_shell_execution:
                return False, f"Command '{base_cmd}' not in allowed list"
        
        return True, "Passed basic checks"
    
    def sanitize_path(self, path: str) -> Optional[Path]:
        """
        Sanitize and validate a file path
        
        Returns:
            Resolved path if valid, None if outside allowed directory
        """
        try:
            # Resolve to absolute path
            target = Path(path).resolve()
            
            # Check if within allowed base directory
            allowed_base = self.config.allowed_base_dir.resolve()
            
            # Check for path traversal attacks
            try:
                target.relative_to(allowed_base)
            except ValueError:
                # Path is outside allowed directory
                self.audit('PATH_VIOLATION', {
                    'attempted_path': str(path),
                    'resolved_path': str(target),
                    'allowed_base': str(allowed_base)
                })
                return None
            
            # Check for symlink attacks
            if target.is_symlink():
                real_target = target.resolve()
                try:
                    real_target.relative_to(allowed_base)
                except ValueError:
                    self.audit('SYMLINK_ATTACK', {
                        'symlink': str(target),
                        'points_to': str(real_target)
                    })
                    return None
            
            return target
            
        except Exception as e:
            logger.error(f"Path sanitization error: {e}")
            return None
    
    def check_network_access(self, url: str) -> Tuple[bool, str]:
        """
        Check if network access to URL is allowed
        
        Returns:
            (is_allowed, reason)
        """
        # Extract hostname from URL
        match = re.match(r'https?://([^/:]+)', url)
        if not match:
            return False, "Invalid URL"
        
        hostname = match.group(1)
        
        # Check whitelist first
        if self.config.allowed_hosts:
            if hostname in self.config.allowed_hosts:
                return True, "Host in whitelist"
        
        # Check for internal IPs
        if self.config.block_internal_ips:
            try:
                # Try to resolve and check IP
                import socket
                ip = socket.gethostbyname(hostname)
                ip_obj = ipaddress.ip_address(ip)
                
                # Check for private/reserved ranges
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
                    self.audit('BLOCKED_INTERNAL_IP', {
                        'url': url,
                        'hostname': hostname,
                        'resolved_ip': ip
                    })
                    return False, f"Access to internal IP {ip} is blocked"
                    
            except socket.gaierror:
                # Couldn't resolve - might be invalid hostname
                pass
        
        # Check for cloud metadata endpoints
        if self.config.block_metadata_endpoints:
            metadata_hosts = [
                '169.254.169.254',  # AWS, GCP, Azure metadata
                'metadata.google.internal',
                'metadata.aws.internal',
                '169.254.170.2',  # AWS ECS
            ]
            if hostname in metadata_hosts or 'metadata' in hostname:
                self.audit('BLOCKED_METADATA', {'url': url})
                return False, "Access to cloud metadata endpoints is blocked"
        
        return True, "Network access allowed"
    
    def redact_secrets(self, text: str) -> str:
        """Redact secrets from text output"""
        redacted = text
        for pattern, replacement in SECRET_PATTERNS:
            redacted = re.sub(pattern, replacement, redacted)
        return redacted
    
    def check_jailbreak(self, text: str) -> Tuple[bool, str]:
        """
        Check for jailbreak/prompt injection attempts
        
        Returns:
            (is_safe, reason)
        """
        for pattern in self.jailbreak_patterns:
            if pattern.search(text):
                self.audit('JAILBREAK_ATTEMPT', {
                    'pattern': pattern.pattern[:50],
                    'input_preview': text[:100]
                })
                return False, "Potential prompt injection detected"
        
        return True, "Input appears safe"
    
    def check_file_size(self, filepath: Path) -> Tuple[bool, str]:
        """Check if file size is within limits"""
        try:
            size_mb = filepath.stat().st_size / (1024 * 1024)
            if size_mb > self.config.max_file_size_mb:
                return False, f"File size {size_mb:.1f}MB exceeds limit of {self.config.max_file_size_mb}MB"
            return True, "File size OK"
        except Exception as e:
            return False, f"Cannot check file size: {e}"
    
    def execute_safely(self, command: str, timeout: int = None) -> Dict:
        """
        Execute a command with full security checks
        
        Returns:
            Dict with 'success', 'output', 'error'
        """
        # Check for jailbreak in command
        safe, reason = self.check_jailbreak(command)
        if not safe:
            return {
                'success': False,
                'output': '',
                'error': f'Security violation: {reason}'
            }
        
        # Check command safety
        safe, reason = self.check_command(command)
        if not safe:
            return {
                'success': False,
                'output': '',
                'error': f'Command blocked: {reason}'
            }
        
        # Execute with timeout
        timeout = timeout or self.config.command_timeout
        
        try:
            self.audit('COMMAND_EXEC', {'command': command[:100]})
            
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.config.allowed_base_dir
            )
            
            # Truncate output if too long
            output = result.stdout
            lines = output.split('\n')
            if len(lines) > self.config.max_output_lines:
                output = '\n'.join(lines[:self.config.max_output_lines])
                output += f"\n\n... (truncated {len(lines) - self.config.max_output_lines} lines)"
            
            # Redact any secrets in output
            output = self.redact_secrets(output)
            stderr = self.redact_secrets(result.stderr)
            
            return {
                'success': result.returncode == 0,
                'output': output,
                'error': stderr if result.returncode != 0 else ''
            }
            
        except subprocess.TimeoutExpired:
            self.audit('COMMAND_TIMEOUT', {'command': command[:100], 'timeout': timeout})
            return {
                'success': False,
                'output': '',
                'error': f'Command timed out after {timeout} seconds'
            }
        except Exception as e:
            return {
                'success': False,
                'output': '',
                'error': f'Execution error: {str(e)}'
            }
    
    def check_rate_limit(self, session_id: str) -> Tuple[bool, str]:
        """
        Check if a session is within its rate limit using a sliding window.

        Tracks requests per session_id over the configured window and enforces
        the rate_limit_per_minute cap defined in SecurityConfig.

        Returns:
            (is_allowed, reason)
        """
        now = time.time()
        window_seconds = self.config.rate_limit_window_seconds
        max_requests = self.config.rate_limit_per_minute

        # Prune timestamps outside the current window
        window_start = now - window_seconds
        self._rate_limit_store[session_id] = [
            t for t in self._rate_limit_store[session_id] if t > window_start
        ]

        current_count = len(self._rate_limit_store[session_id])

        if current_count >= max_requests:
            self.audit('RATE_LIMIT_EXCEEDED', {
                'session_id': session_id,
                'requests_in_window': current_count,
                'limit': max_requests,
                'window_seconds': window_seconds
            })
            return False, (
                f"Rate limit exceeded: {current_count} requests in the last "
                f"{window_seconds}s (max {max_requests})"
            )

        # Record this request
        self._rate_limit_store[session_id].append(now)
        return True, f"Rate limit OK ({current_count + 1}/{max_requests})"

    def check_message_size(self, message: str) -> Tuple[bool, str]:
        """Check if message is within size limits"""
        if len(message) > self.config.max_message_length:
            return False, f"Message too long ({len(message)} chars). Max: {self.config.max_message_length}"
        return True, "Message size OK"
    
    def check_disk_usage(self) -> Tuple[bool, str]:
        """Check if agent is within disk usage limits"""
        try:
            import shutil
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(self.config.allowed_base_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
            
            total_mb = total_size / (1024 * 1024)
            if total_mb > self.config.max_disk_usage_mb:
                return False, f"Disk usage ({total_mb:.1f}MB) exceeds limit ({self.config.max_disk_usage_mb}MB)"
            return True, f"Disk usage: {total_mb:.1f}MB / {self.config.max_disk_usage_mb}MB"
        except Exception as e:
            return True, f"Could not check disk usage: {e}"
    
    def check_memory_usage(self) -> Tuple[bool, str]:
        """Check if agent process is within memory limits"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / (1024 * 1024)
            
            if mem_mb > self.config.max_memory_usage_mb:
                return False, f"Memory usage ({mem_mb:.1f}MB) exceeds limit ({self.config.max_memory_usage_mb}MB)"
            return True, f"Memory usage: {mem_mb:.1f}MB / {self.config.max_memory_usage_mb}MB"
        except ImportError:
            return True, "psutil not available, skipping memory check"
        except Exception as e:
            return True, f"Could not check memory: {e}"
    
    def get_resource_status(self) -> Dict:
        """Get current resource usage status"""
        disk_ok, disk_msg = self.check_disk_usage()
        mem_ok, mem_msg = self.check_memory_usage()
        
        return {
            'disk_usage': disk_msg,
            'disk_ok': disk_ok,
            'memory_usage': mem_msg,
            'memory_ok': mem_ok,
            'limits': {
                'max_file_size_mb': self.config.max_file_size_mb,
                'max_disk_usage_mb': self.config.max_disk_usage_mb,
                'max_memory_usage_mb': self.config.max_memory_usage_mb,
                'command_timeout': self.config.command_timeout,
                'max_output_lines': self.config.max_output_lines,
                'max_message_length': self.config.max_message_length,
                'max_daily_commands': self.config.max_daily_commands,
                'rate_limit_per_minute': self.config.rate_limit_per_minute,
            }
        }


# Global security manager instance
_default_security = None

def get_security_manager(config: SecurityConfig = None) -> SecurityManager:
    """Get or create global security manager"""
    global _default_security
    if _default_security is None:
        _default_security = SecurityManager(config)
    return _default_security