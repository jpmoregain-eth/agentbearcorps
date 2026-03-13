# 🐻 Agent Bear Corps - Agent Bear Corps

**Your personal AI agent. Multi-provider. Multi-personality. Yours to command.**

---

## 🤔 What is Agent Bear Corps?

Agent Bear Corps lets you create your own AI agent that:
- **Chats with you** like a personal assistant
- **Remembers conversations** (persistent memory)
- **Uses multiple AI brains** (Anthropic, OpenAI, Google, etc.)
- **Has different personalities** (professional, funny, technical, etc.)
- **Runs on your computer** (your data stays private)

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Download

```bash
git clone https://github.com/jpmoregain-eth/Agent Bear Corps.git
cd Agent Bear Corps
```

### Step 2: Install

```bash
pip install -r requirements.txt
```

> 💡 **Tip:** If you get permission errors, try `pip3` instead of `pip`

### Step 3: Run Setup Wizard

```bash
python setup.py
```

This will:
1. **Open your browser** automatically (at http://localhost:8080)
2. **Guide you through 6 simple steps** to configure your agent
3. **Save your configuration** as a YAML file
4. **Launch your agent** (optional)

---

## 🎮 How to Use Your Agent

### Option A: Chat in Terminal

```bash
python agentbear.py chat --config my-agent.yaml
```

Type your messages, press Enter. Type `exit` to quit.

### Option B: Start API Server

```bash
python agentbear.py api --config my-agent.yaml --port 5000
```

Then talk to your agent via API:
```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}'
```

### Option C: Interactive Mode

```bash
# Show agent info
python agentbear.py info --config my-agent.yaml

# Quick single message
python agentbear.py chat -m "What's the weather like?" --config my-agent.yaml
```

---

## 📁 File Structure

After setup, you'll have:

```
Agent Bear Corps/
├── setup.py              ← Run this first (opens browser wizard)
├── agentbear.py          ← CLI tool to chat with your agent
├── my-agent.yaml         ← Your agent's config (created by wizard)
├── my-agent_memory.db    ← Conversation history
└── requirements.txt      ← Dependencies
```

---

## 🔑 Getting API Keys

Your agent needs API keys to talk to AI services. Here's how to get them:

### Anthropic (Claude) - Recommended ⭐
1. Go to https://console.anthropic.com
2. Sign up / Log in
3. Click "Get API Keys"
4. Create new key
5. Copy the key (starts with `sk-ant-`)

### OpenAI (GPT)
1. Go to https://platform.openai.com
2. Sign up / Log in
3. Go to "API Keys" in settings
4. Create new secret key
5. Copy the key (starts with `sk-`)

### Google (Gemini)
1. Go to https://ai.google.dev
2. Sign up with Google account
3. Get API key

### Others
- **xAI (Grok)**: https://console.x.ai
- **DeepSeek**: https://platform.deepseek.com
- **Alibaba (Qwen)**: https://dashscope.aliyun.com

> ⚠️ **Important:** Keep your API keys secret! Don't share them or commit them to git.

---

## 🎭 Personalities (Personas)

Choose how your agent talks:

| Persona | Style |
|---------|-------|
| **Professional** | Formal, business-like, concise |
| **Friendly** | Warm, approachable, conversational |
| **Technical** | Precise, detailed, uses tech terms |
| **Teacher** | Patient, explanatory, educational |
| **Creative** | Imaginative, suggests ideas |
| **Humorous** | Witty, playful, tells jokes |

**You can combine multiple!** Try "Professional + Humorous" for a funny but capable assistant.

---

## 🧠 AI Models Available

### 🇺🇸 American Models

| Provider | Best Models | Use Case |
|----------|-------------|----------|
| **Anthropic** | Claude Sonnet 4.6 ⭐ | Best overall, coding |
| **OpenAI** | GPT-5.4 | General purpose |
| **Google** | Gemini 3 Pro | Long documents (2M context) |
| **xAI** | Grok-4 | Real-time knowledge |

### 🇨🇳 Chinese Models

| Provider | Best Models | Use Case |
|----------|-------------|----------|
| **DeepSeek** | V3.2 | Open-source coding |
| **Alibaba** | Qwen3.5-Plus | Versatile agent |
| **Moonshot** | Kimi K2.5 | Long context (256K) |
| **Baidu** | ERNIE 5.0 | Multimodal |

---

## ❓ Troubleshooting

### "pip not found"
Try `pip3` instead of `pip`

### "Permission denied"
Add `--user` flag:
```bash
pip install --user -r requirements.txt
```

### "Module not found"
Make sure you're in the `Agent Bear Corps` directory:
```bash
cd Agent Bear Corps
python setup.py
```

### "Port already in use"
Change the port:
```bash
python setup.py --port 8081
# or
python agentbear.py api --port 5001
```

### "No module named 'anthropic'"
Install the specific provider:
```bash
pip install anthropic
# or
pip install openai
# etc.
```

---

## 🔧 Advanced Usage

### Create Multiple Agents

```bash
# Create agent for work
python setup.py  # Save as work-agent.yaml

# Create agent for fun
python setup.py  # Save as fun-agent.yaml

# Switch between them
python agentbear.py chat --config work-agent.yaml
python agentbear.py chat --config fun-agent.yaml
```

### Manual Config Editing

You can edit the YAML file directly:

```yaml
agent:
  name: my-super-agent
  personas:
    - professional
    - humorous
  
models:
  primary: claude-sonnet-4-6
  providers:
    anthropic:
      api_key: "sk-ant-..."
    openai:
      api_key: "sk-..."
```

### Environment Variables

Instead of putting API keys in the config file, you can use environment variables:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
```

---

## 📊 What's Inside?

- **🧠 agent.py** - The brain of your agent
- **💾 memory.py** - Remembers your conversations
- **🔌 providers.py** - Connects to different AI services
- **🌐 api_server.py** - Web interface for external tools
- **⚙️ config.py** - Handles your settings
- **🎨 templates/** - Pretty web interface

---

## 🤝 Need Help?

1. Check the [troubleshooting](#-troubleshooting) section above
2. Make sure you have Python 3.8 or higher
3. Ensure all dependencies are installed

---

## 📜 License

MIT License - Agent Bear Corps 🐻

**Made with ❤️ for the AI community**