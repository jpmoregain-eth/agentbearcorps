"""
HTTP API Server for ABC AI
Exposes endpoints for external tools to call the agent

Security hardening:
- API key authentication on all non-health endpoints
- CORS restricted to configured allowed origins
- Rate limiting per client IP
- Host defaults to localhost only
- yaml import fixed
- /health no longer leaks internal config details
"""

import os
import sys
import yaml
import logging
import time
from collections import defaultdict
from functools import wraps
from pathlib import Path
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from typing import Dict, Any, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))
from agent import ABCAIAgent
from config import AgentConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiter (in-memory, per IP)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple sliding-window rate limiter keyed by IP address."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > window_start]
        if len(self._requests[key]) >= self.max_requests:
            return False
        self._requests[key].append(now)
        return True


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _load_api_key() -> Optional[str]:
    """
    Load the server API key from the environment variable ABC_API_KEY.
    If not set, authentication is DISABLED and a loud warning is logged.
    """
    key = os.environ.get("ABC_API_KEY", "").strip()
    if not key:
        logger.warning(
            "WARNING: ABC_API_KEY is not set. API authentication is DISABLED. "
            "Set ABC_API_KEY=<secret> in your environment before running in production."
        )
    return key or None


class ABCAIAPI:
    """HTTP API wrapper for ABC AI Agent"""

    def __init__(self, config_path: str = "agent_config.yaml", port: int = 5000,
                 allowed_origins: list = None):
        self.config_path = config_path
        self.port = port
        self.agent = ABCAIAgent(config_path)
        self.api_key = _load_api_key()
        self.rate_limiter = RateLimiter(
            max_requests=int(os.environ.get("ABC_RATE_LIMIT", "30")),
            window_seconds=60,
        )

        # CORS: only allow explicitly configured origins (defaults to localhost)
        origins = allowed_origins or os.environ.get(
            "ABC_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")

        self.app = Flask(__name__)
        CORS(self.app, origins=origins, supports_credentials=False)
        self._setup_routes()

    # ------------------------------------------------------------------
    # Decorators
    # ------------------------------------------------------------------

    def _require_auth(self, f):
        """Decorator: enforce API key authentication."""
        @wraps(f)
        def decorated(*args, **kwargs):
            if self.api_key is None:
                logger.debug("Auth disabled — request allowed without key")
                return f(*args, **kwargs)

            auth_header = request.headers.get("Authorization", "")
            provided_key = ""
            if auth_header.startswith("Bearer "):
                provided_key = auth_header[7:]
            else:
                provided_key = request.headers.get("X-API-Key", "")

            if provided_key != self.api_key:
                logger.warning(
                    "Unauthorized request from %s to %s",
                    request.remote_addr, request.path
                )
                return jsonify({"error": "Unauthorized"}), 401

            return f(*args, **kwargs)
        return decorated

    def _rate_limit(self, f):
        """Decorator: apply per-IP rate limiting."""
        @wraps(f)
        def decorated(*args, **kwargs):
            client_ip = request.remote_addr or "unknown"
            if not self.rate_limiter.is_allowed(client_ip):
                logger.warning("Rate limit exceeded for %s on %s", client_ip, request.path)
                return jsonify({"error": "Too many requests — slow down"}), 429
            return f(*args, **kwargs)
        return decorated

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    def _setup_routes(self):
        """Setup Flask routes"""

        require_auth = self._require_auth
        rate_limit = self._rate_limit

        @self.app.route('/health', methods=['GET'])
        def health():
            """Minimal health check — does not leak internal config."""
            return jsonify({'status': 'healthy'})

        @self.app.route('/api/info', methods=['GET'])
        @require_auth
        @rate_limit
        def info():
            return jsonify(self.agent.get_info())

        @self.app.route('/api/chat', methods=['POST'])
        @require_auth
        @rate_limit
        def chat():
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
                logger.error("Chat failed: %s", e)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/chat/stream', methods=['POST'])
        @require_auth
        @rate_limit
        def chat_stream():
            data = request.json or {}
            message = data.get('message', '')
            session_id = data.get('session_id')

            if not message:
                return jsonify({'error': 'message is required'}), 400

            try:
                result = self.agent.chat(message, session_id)
                return jsonify(result)
            except Exception as e:
                logger.error("Chat stream failed: %s", e)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/memory/<session_id>', methods=['GET'])
        @require_auth
        @rate_limit
        def get_memory(session_id):
            try:
                history = self.agent.get_memory(session_id)
                return jsonify({
                    'session_id': session_id,
                    'messages': history,
                    'count': len(history)
                })
            except Exception as e:
                logger.error("Get memory failed: %s", e)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/memory/<session_id>', methods=['DELETE'])
        @require_auth
        @rate_limit
        def clear_memory(session_id):
            try:
                self.agent.clear_memory(session_id)
                return jsonify({
                    'success': True,
                    'message': f'Memory cleared for session {session_id}'
                })
            except Exception as e:
                logger.error("Clear memory failed: %s", e)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/model', methods=['GET'])
        @require_auth
        @rate_limit
        def get_model():
            return jsonify({
                'primary_model': self.agent.config.primary_model,
                'available_providers': list(self.agent.providers.keys()),
                'personas': self.agent.config.personas
            })

        @self.app.route('/api/model', methods=['POST'])
        @require_auth
        @rate_limit
        def switch_model():
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
                    return jsonify({'error': f'Failed to switch to model {model_id}'}), 400
            except Exception as e:
                logger.error("Switch model failed: %s", e)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/config', methods=['GET'])
        @require_auth
        @rate_limit
        def get_config():
            return jsonify(self.agent.config.to_dict())

        @self.app.route('/api/config', methods=['POST'])
        @require_auth
        @rate_limit
        def update_config():
            data = request.json or {}
            try:
                config_dict = self.agent.config.to_dict()
                config_dict.update(data)

                # yaml is now properly imported at top of file (was missing before)
                with open(self.config_path, 'w') as f:
                    yaml.dump(config_dict, f, default_flow_style=False)

                self.agent = ABCAIAgent(self.config_path)

                return jsonify({
                    'success': True,
                    'message': 'Configuration updated and agent reloaded'
                })
            except Exception as e:
                logger.error("Update config failed: %s", e)
                return jsonify({'error': str(e)}), 500

    def run(self, host='127.0.0.1', debug=False):
        """
        Run the API server.

        Host defaults to 127.0.0.1 (localhost only).
        Use host='0.0.0.0' only with a firewall or reverse proxy in front.
        """
        logger.info("ABC AI API Server starting on %s:%s", host, self.port)
        logger.info("   Config: %s", self.config_path)
        logger.info("   Agent: %s", self.agent.config.name)
        logger.info("   Auth: %s", "ENABLED" if self.api_key else "DISABLED - set ABC_API_KEY")
        logger.info("   Endpoints: http://%s:%s/api/", host, self.port)
        self.app.run(host=host, port=self.port, debug=debug)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='ABC AI API Server')
    parser.add_argument('--config', default='agent_config.yaml', help='Config file path')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    parser.add_argument(
        '--host', default='127.0.0.1',
        help='Host to bind to. Default: 127.0.0.1. Use 0.0.0.0 with caution.'
    )
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument(
        '--allowed-origins', default=None,
        help='Comma-separated allowed CORS origins'
    )

    args = parser.parse_args()
    allowed_origins = args.allowed_origins.split(',') if args.allowed_origins else None

    api = ABCAIAPI(args.config, args.port, allowed_origins=allowed_origins)
    api.run(host=args.host, debug=args.debug)
