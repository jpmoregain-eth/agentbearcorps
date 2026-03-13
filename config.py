"""
ABC AI - Agent Bear Corps Runtime
Multi-provider AI agent with memory and API
"""

import os
import sys
import yaml
import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for ABC AI Agent"""
    name: str = "abc-agent"
    owner: str = "user"
    personas: List[str] = field(default_factory=list)
    language: str = "en"
    version: str = "1.0.0"
    
    # Models config
    primary_model: str = "claude-sonnet-4-6"
    providers: Dict[str, Dict] = field(default_factory=dict)
    
    # Capabilities
    capabilities: Dict[str, Any] = field(default_factory=dict)
    
    # Memory
    memory_enabled: bool = True
    memory_db_path: str = "agent_memory.db"
    
    @classmethod
    def from_yaml(cls, config_path: str) -> 'AgentConfig':
        """Load config from YAML file"""
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
        
        config = cls()
        
        # Agent section
        agent = data.get('agent', {})
        config.name = agent.get('name', 'abc-agent')
        config.owner = agent.get('owner', 'user')
        config.personas = agent.get('personas', ['professional'])
        if isinstance(config.personas, str):
            config.personas = [config.personas]
        config.language = agent.get('language', 'en')
        config.version = agent.get('version', '1.0.0')
        
        # Models section
        models = data.get('models', {})
        config.primary_model = models.get('primary', 'claude-sonnet-4-6')
        config.providers = models.get('providers', {})
        
        # Capabilities
        config.capabilities = data.get('capabilities', {})
        
        # Memory
        memory = data.get('memory', {})
        config.memory_enabled = memory.get('enabled', True)
        config.memory_db_path = memory.get('db_path', 'agent_memory.db')
        
        return config
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'agent': {
                'name': self.name,
                'owner': self.owner,
                'personas': self.personas,
                'language': self.language,
                'version': self.version
            },
            'models': {
                'primary': self.primary_model,
                'providers': self.providers
            },
            'capabilities': self.capabilities,
            'memory': {
                'enabled': self.memory_enabled,
                'db_path': self.memory_db_path
            }
        }