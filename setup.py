#!/usr/bin/env python3
"""
ABC AI Setup - One-command setup wizard
Opens browser for configuration, then launches agent
"""

import os
import sys
import time
import json
import yaml
import logging
import webbrowser
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import setup wizard from setup_wizard module
sys.path.insert(0, str(Path(__file__).parent))
from setup_wizard import setup, complete, save_progress, load_progress

# Create Flask app for setup
app = Flask(__name__)
app.secret_key = 'abc-setup-secret-key'

# Re-register routes from setup_wizard
app.route('/')(lambda: redirect('/setup/1'))
app.route('/setup')(lambda: redirect('/setup/1'))
app.route('/setup/<int:step>', methods=['GET', 'POST'])(setup)
app.route('/complete')(complete)

# Track if setup is done
setup_completed = False
config_path = None


@app.route('/api/generate-config', methods=['POST'])
def generate_config():
    """Generate agent configuration - launches agent after"""
    global setup_completed, config_path
    
    data = request.json or {}
    progress = load_progress()
    
    # Build config
    agent_name = progress.get('step_1', {}).get('agent_name', 'my-agent')
    
    config = {
        'agent': {
            'name': agent_name,
            'owner': progress.get('step_1', {}).get('owner_name', 'user'),
            'personas': progress.get('step_2', {}).get('personas', ['professional']),
            'language': progress.get('step_1', {}).get('language', 'en'),
            'version': '1.0.0'
        },
        'models': {
            'primary': progress.get('step_3', {}).get('primary_model', 'claude-sonnet-4-6'),
            'providers': {}
        },
        'capabilities': {},
        'memory': {
            'enabled': True,
            'db_path': f'{agent_name}_memory.db'
        }
    }
    
    # Add provider API keys
    providers = progress.get('step_3', {}).get('providers', [])
    for provider in providers:
        api_key_field = f'api_key_{provider}'
        api_key = progress.get('step_3', {}).get(api_key_field, '')
        if api_key:
            config['models']['providers'][provider] = {'api_key': api_key}
    
    # Add capabilities
    capabilities = progress.get('step_4', {}).get('capabilities', [])
    for cap in capabilities:
        config['capabilities'][cap] = {'enabled': True}
    
    # Save config file
    config_path = f'{agent_name}.yaml'
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    setup_completed = True
    
    return jsonify({
        'success': True,
        'config_path': config_path,
        'config': config
    })


@app.route('/api/launch', methods=['POST'])
def launch_agent():
    """Launch the agent after setup"""
    global config_path
    
    data = request.json or {}
    auto_launch = data.get('auto_launch', True)
    
    if not config_path or not Path(config_path).exists():
        return jsonify({'error': 'Config not found'}), 400
    
    if auto_launch:
        # Start agent in background thread
        def run_agent():
            time.sleep(1)  # Give browser time to show success
            logger.info(f"🐻 Launching agent with config: {config_path}")
            
            # Import and run agent
            from agent import ABCAIAgent
            from api_server import ABCAIAPI
            
            api = ABCAIAPI(config_path, port=5000)
            api.run()
        
        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Agent launching on http://localhost:5000',
            'config_path': config_path
        })
    
    return jsonify({
        'success': True,
        'message': f'Config saved to {config_path}. Run: python agentbear.py chat --config {config_path}'
    })


def open_browser():
    """Open browser after short delay"""
    time.sleep(2)
    url = 'http://localhost:8080'
    logger.info(f'🌐 Opening browser: {url}')
    webbrowser.open(url)


def main():
    """Main setup entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ABC AI Setup Wizard')
    parser.add_argument('--port', type=int, default=8080, help='Port for setup wizard')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser automatically')
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("🐻 ABC AI - Agent Bear Corps Setup")
    print("=" * 50)
    print()
    print("This wizard will help you configure your AI agent.")
    print()
    
    if not args.no_browser:
        # Open browser in background thread
        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()
        print("🌐 Opening browser...")
    else:
        print(f"🌐 Open http://localhost:{args.port} in your browser")
    
    print()
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    try:
        app.run(host='0.0.0.0', port=args.port, debug=False)
    except KeyboardInterrupt:
        print("\n\n👋 Setup cancelled")
        sys.exit(0)


if __name__ == '__main__':
    main()