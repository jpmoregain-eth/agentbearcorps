"""
ABC Setup Wizard - Agent Bear Corps
Universal agent setup and spawning system
"""

import os
import sys
import json
import yaml
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from flask import Flask, render_template, request, jsonify, redirect, url_for
from cryptography.fernet import Fernet

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Use a fixed secret key for Vercel (sessions won't persist across deployments but work within one)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'abc-setup-dev-key-2026')

# For Vercel serverless - use Flask session instead of file storage
from flask import session

# Constants
REGISTRY_PATH = Path.home() / '.agentbear' / 'registry.json'
KEY_FILE = Path.home() / '.agentbear' / '.master_key'
CONFIG_DIR = Path(__file__).parent / 'config'

def load_yaml_config(filename: str) -> dict:
    """Load configuration from YAML file"""
    config_path = CONFIG_DIR / filename
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return {}
    
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load {filename}: {e}")
        return {}

# Load configurations from YAML
AI_PROVIDERS = load_yaml_config('providers.yaml')
CAPABILITIES = load_yaml_config('capabilities.yaml')
PERSONAS = load_yaml_config('personas.yaml')
LANGUAGES = load_yaml_config('languages.yaml')


def get_or_create_key() -> bytes:
    """Get or create encryption key"""
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    if KEY_FILE.exists():
        with open(KEY_FILE, 'rb') as f:
            return f.read()
    
    key = Fernet.generate_key()
    with open(KEY_FILE, 'wb') as f:
        f.write(key)
    os.chmod(KEY_FILE, 0o600)
    return key


def encrypt_value(value: str) -> str:
    """Encrypt a value"""
    if not value or value.startswith('ENC:'):
        return value
    
    key = get_or_create_key()
    cipher = Fernet(key)
    encrypted = cipher.encrypt(value.encode())
    return f"ENC:{encrypted.decode()}"


@app.route('/')
def index():
    """Landing page - redirects to setup"""
    return redirect(url_for('setup', step=1))


@app.route('/setup')
def setup_redirect():
    """Redirect to step 1"""
    return redirect(url_for('setup', step=1))


@app.route('/setup/<int:step>', methods=['GET', 'POST'])
def setup(step):
    """Setup wizard steps"""
    if step < 1 or step > 6:
        return redirect(url_for('setup', step=1))
    
    if request.method == 'POST':
        # Save progress to session - handle MultiDict properly
        form_data = {}
        for key in request.form:
            # Get all values for this key (handles multiple checkboxes)
            values = request.form.getlist(key)
            if len(values) == 1:
                form_data[key] = values[0]
            else:
                form_data[key] = values
        
        save_progress(step, form_data)
        
        if step < 6:
            return redirect(url_for('setup', step=step + 1))
        else:
            return redirect(url_for('complete'))
    
    # Load existing progress
    progress = load_progress()
    
    return render_template(
        f'step{step}.html',
        step=step,
        progress=progress,
        ai_providers=AI_PROVIDERS,
        capabilities=CAPABILITIES,
        personas=PERSONAS,
        languages=LANGUAGES
    )


@app.route('/complete')
def complete():
    """Completion page"""
    return render_template('complete.html')


@app.route('/api/generate-config', methods=['POST'])
def generate_config():
    """Generate agent configuration - Vercel compatible (no file write)"""
    data = request.json
    
    config = build_config(data)
    
    # Return config as YAML string (no file write on Vercel)
    config_yaml = yaml.dump(config, default_flow_style=False)
    
    return jsonify({
        'success': True,
        'config_yaml': config_yaml,
        'config': config
    })


@app.route('/api/launch', methods=['POST'])
def launch_agent():
    """Launch the generated agent - Actually starts the runtime"""
    import subprocess
    import sys
    
    data = request.json
    agent_name = data.get('agent_name', 'my-agent')
    
    try:
        # Build config from session data (includes encrypted API key!)
        progress = load_progress()
        
        # Combine all step data
        wizard_data = {}
        for step_data in progress.values():
            wizard_data.update(step_data)
        
        # Build full config with API key
        config = build_config(wizard_data)
        config_yaml = yaml.dump(config, default_flow_style=False)
        
        # Save config to file
        config_path = Path.home() / '.agentbear' / 'agents' / f'{agent_name}.yaml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            f.write(config_yaml)
        
        # Start the agent in background
        agent_script = Path(__file__).parent / 'agent.py'
        process = subprocess.Popen(
            [sys.executable, str(agent_script), str(config_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path(__file__).parent)
        )
        
        # Register in registry
        registry_path = Path.home() / '.agentbear' / 'registry.json'
        registry = {}
        if registry_path.exists():
            with open(registry_path, 'r') as f:
                registry = json.load(f)
        
        registry[agent_name] = {
            'config_path': str(config_path),
            'pid': process.pid,
            'created_at': datetime.now().isoformat(),
            'status': 'running'
        }
        
        with open(registry_path, 'w') as f:
            json.dump(registry, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': f'Agent "{agent_name}" launched successfully!',
            'pid': process.pid,
            'config_path': str(config_path)
        })
        
    except Exception as e:
        logger.error(f"Failed to launch agent: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to launch agent: {str(e)}'
        }), 500


def save_progress(step: int, data: dict):
    """Save wizard progress to Flask session (Vercel-compatible)"""
    # Initialize session progress if not exists
    if 'progress' not in session:
        session['progress'] = {}
    
    # Convert form data to dict and save
    session['progress'][f'step_{step}'] = dict(data)
    session.modified = True


def load_progress() -> dict:
    """Load wizard progress from Flask session"""
    return session.get('progress', {})


def build_config(data: dict) -> dict:
    """Build agent configuration from wizard data"""
    # Get selected capabilities
    selected_caps = data.get('capabilities', [])
    
    # Build config structure
    config = {
        'agent': {
            'name': data.get('agent_name', 'my-agent'),
            'owner': data.get('owner_name', 'anonymous'),
            'language': data.get('language', 'en'),
            'persona': data.get('persona', 'professional'),
            'custom_prompt': data.get('custom_prompt', ''),
            'version': '1.0.0'
        },
        'model': {
            'provider': data.get('provider', 'anthropic'),
            'name': data.get('model_name', 'claude-sonnet-4-6'),
            'endpoint': AI_PROVIDERS[data.get('provider', 'anthropic')]['endpoint'],
            'api_key': encrypt_value(data.get('api_key', '')),
            'max_tokens': 4000,
            'temperature': 0.3
        },
        'capabilities': {},
        'memory': {
            'enabled': True,
            'db_path': 'agent_memory.db'
        }
    }
    
    # Add capability configs
    for cap_id in selected_caps:
        config['capabilities'][cap_id] = {'enabled': True}
        
        # Add API keys for capabilities that need them
        for category in CAPABILITIES.values():
            for item in category['items']:
                if item['id'] == cap_id and item.get('api_key'):
                    key_name = item.get('key_name')
                    if key_name and key_name in data:
                        config['capabilities'][cap_id]['api_key'] = encrypt_value(data[key_name])
    
    return config


if __name__ == '__main__':
    import time
    import threading
    import webbrowser
    
    def open_browser():
        """Open browser after short delay"""
        time.sleep(2)
        webbrowser.open('http://localhost:5000')
    
    print("🐻 ABC Setup Wizard")
    print("=" * 40)
    print("Open http://localhost:5000 in your browser")
    print("=" * 40)
    
    # Start browser in background thread
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    app.run(host='0.0.0.0', port=5000, debug=True)

# For Vercel serverless deployment
# Vercel expects the 'app' variable to be exposed
# The serverless handler will use this directly