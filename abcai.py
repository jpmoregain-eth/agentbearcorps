#!/usr/bin/env python3
"""
ABC AI CLI - Command line interface for the agent
"""

import argparse
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import ABCAIAgent


def main():
    parser = argparse.ArgumentParser(
        description='🐻 ABC AI - Agent Bear Corps',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s chat                    # Interactive chat mode
  %(prog)s chat -m "Hello"         # Single message
  %(prog)s info                    # Show agent info
  %(prog)s api --port 5000         # Start API server
        """
    )
    
    parser.add_argument('--config', '-c', default='agent_config.yaml',
                        help='Config file path (default: agent_config.yaml)')
    parser.add_argument('--version', action='version', version='ABC AI 1.0.0')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Chat command
    chat_parser = subparsers.add_parser('chat', help='Chat with the agent')
    chat_parser.add_argument('--message', '-m', help='Single message to send')
    chat_parser.add_argument('--session', '-s', help='Session ID for memory')
    
    # Info command
    subparsers.add_parser('info', help='Show agent information')
    
    # API command
    api_parser = subparsers.add_parser('api', help='Start API server')
    api_parser.add_argument('--port', '-p', type=int, default=5000,
                            help='Port to run on (default: 5000)')
    api_parser.add_argument('--host', default='0.0.0.0',
                            help='Host to bind to (default: 0.0.0.0)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'info':
        agent = ABCAIAgent(args.config)
        info = agent.get_info()
        
        print("\n🐻 ABC AI Agent")
        print("=" * 40)
        print(f"Name:     {info['name']}")
        print(f"Owner:    {info['owner']}")
        print(f"Personas: {', '.join(info['personas'])}")
        print(f"Model:    {info['primary_model']}")
        print(f"Providers: {', '.join(info['available_providers'])}")
        print(f"Capabilities: {', '.join(info['capabilities'])}")
        print(f"Memory:   {'✓' if info['memory_enabled'] else '✗'}")
        print("=" * 40)
    
    elif args.command == 'chat':
        from datetime import datetime
        
        agent = ABCAIAgent(args.config)
        
        if args.message:
            # Single message
            result = agent.chat(args.message, args.session)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"🤖 {result['response']}")
        else:
            # Interactive mode
            print(f"\n🐻 {agent.config.name} is ready!")
            print(f"   Personas: {', '.join(agent.config.personas)}")
            print(f"   Model: {agent.config.primary_model}")
            print("\nType 'exit' or 'quit' to stop")
            print("-" * 40)
            
            session_id = args.session or f"cli_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
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
                        print(f"\n🤖 {result['response']}")
                        
                except KeyboardInterrupt:
                    break
                except EOFError:
                    break
            
            print("\n👋 Goodbye!")
    
    elif args.command == 'api':
        from api_server import ABCAIAPI
        
        api = ABCAIAPI(args.config, args.port)
        api.run(host=args.host)


if __name__ == '__main__':
    main()