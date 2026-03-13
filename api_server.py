"""
HTTP API Server for ABC AI
Exposes endpoints for external tools to call the agent
"""

import os
import sys
import logging
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from typing import Dict, Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))
from agent import ABCAIAgent
from config import AgentConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ABCAIAPI:
    """HTTP API wrapper for ABC AI Agent"""
    
    def __init__(self, config_path: str = "agent_config.yaml", port: int = 5000):
        self.config_path = config_path
        self.port = port
        self.agent = ABCAIAgent(config_path)
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for all routes
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/health', methods=['GET'])
        def health():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'agent': self.agent.config.name,
                'port': self.port,
                'providers': list(self.agent.providers.keys()),
                'model': self.agent.config.primary_model
            })
        
        @self.app.route('/api/info', methods=['GET'])
        def info():
            """Get agent information"""
            return jsonify(self.agent.get_info())
        
        @self.app.route('/api/chat', methods=['POST'])
        def chat():
            """Send a chat message to the agent"""
            data = request.json or {}
            message = data.get('message', '')
            session_id = data.get('session_id')
            context = data.get('context', {})
            
            if not message:
                return jsonify({'error': 'message is required'}), 400
            
            try:
                result = self.agent.chat(message, session_id, context)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Chat failed: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/chat/stream', methods=['POST'])
        def chat_stream():
            """Send a chat message and get streaming response (placeholder)"""
            # For now, just return the regular response
            data = request.json or {}
            message = data.get('message', '')
            session_id = data.get('session_id')
            
            if not message:
                return jsonify({'error': 'message is required'}), 400
            
            try:
                result = self.agent.chat(message, session_id)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Chat stream failed: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/memory/<session_id>', methods=['GET'])
        def get_memory(session_id):
            """Get conversation history for a session"""
            try:
                history = self.agent.get_memory(session_id)
                return jsonify({
                    'session_id': session_id,
                    'messages': history,
                    'count': len(history)
                })
            except Exception as e:
                logger.error(f"Get memory failed: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/memory/<session_id>', methods=['DELETE'])
        def clear_memory(session_id):
            """Clear memory for a session"""
            try:
                self.agent.clear_memory(session_id)
                return jsonify({
                    'success': True,
                    'message': f'Memory cleared for session {session_id}'
                })
            except Exception as e:
                logger.error(f"Clear memory failed: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/model', methods=['GET'])
        def get_model():
            """Get current model info"""
            return jsonify({
                'primary_model': self.agent.config.primary_model,
                'available_providers': list(self.agent.providers.keys()),
                'personas': self.agent.config.personas
            })
        
        @self.app.route('/api/model', methods=['POST'])
        def switch_model():
            """Switch primary model"""
            data = request.json or {}
            model_id = data.get('model_id')
            
            if not model_id:
                return jsonify({'error': 'model_id is required'}), 400
            
            try:
                success = self.agent.switch_model(model_id)
                if success:
                    return jsonify({
                        'success': True,
                        'message': f'Switched to model {model_id}',
                        'primary_model': model_id
                    })
                else:
                    return jsonify({
                        'error': f'Failed to switch to model {model_id}'
                    }), 400
            except Exception as e:
                logger.error(f"Switch model failed: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/config', methods=['GET'])
        def get_config():
            """Get agent configuration"""
            return jsonify(self.agent.config.to_dict())
        
        @self.app.route('/api/config', methods=['POST'])
        def update_config():
            """Update agent configuration (reloads agent)"""
            data = request.json or {}
            
            # Save config to file
            try:
                config_dict = self.agent.config.to_dict()
                config_dict.update(data)
                
                with open(self.config_path, 'w') as f:
                    yaml.dump(config_dict, f, default_flow_style=False)
                
                # Reload agent
                self.agent = ABCAIAgent(self.config_path)
                
                return jsonify({
                    'success': True,
                    'message': 'Configuration updated and agent reloaded'
                })
            except Exception as e:
                logger.error(f"Update config failed: {e}")
                return jsonify({'error': str(e)}), 500
    
    def run(self, host='0.0.0.0', debug=False):
        """Run the API server"""
        logger.info(f"🐻 ABC AI API Server starting on port {self.port}")
        logger.info(f"   Config: {self.config_path}")
        logger.info(f"   Agent: {self.agent.config.name}")
        logger.info(f"   Endpoints: http://{host}:{self.port}/api/")
        self.app.run(host=host, port=self.port, debug=debug)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='ABC AI API Server')
    parser.add_argument('--config', default='agent_config.yaml', help='Config file path')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    api = ABCAIAPI(args.config, args.port)
    api.run(host=args.host, debug=args.debug)