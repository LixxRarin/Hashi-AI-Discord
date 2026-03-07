<div align="center">

<img src="character_cards/hashi.png" alt="Hashi" width="120" style="border-radius: 50%;"/>

# Project Hashi - 橋
### AI Characters to Discord Servers

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)  [![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://www.python.org/downloads/)

</div>

> This is an improved fork of the original [Hashi Character.AI Discord Bot](https://github.com/LixxRarin/Hashi-CharacterAI-Discord), completely rewritten to support multiple AI providers (OpenAI, DeepSeek, Claude, Ollama, Custom Endpoint), Character Card V3, and advanced conversation management features!

Project Hashi allows AI personas to interact with users in your Discord server using various AI providers. Perfect for bringing AI personalities to your community with full control over their behavior and appearance.

---

<div align="center">

<img src="imgs/prtscr01.png" alt="Hashi in action" width="650"/>

</div>

---


**Demo Server**: [Join Discord (Not available at the moment)](https://discord.gg/******) | **Report Issues**: [GitHub Issues](https://github.com/LixxRarin/Hashi-AI-Discord/issues)

## Contents
- [🌟 Features](#-features)
- [✨ What's New](#-whats-new)
- [⚠️ Warnings](#️-warnings)
- [🛠️ Setup Guide](#️-setup-guide)
  - [Prerequisites](#prerequisites)
  - [Discord Bot Creation](#discord-bot-creation)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Setup Bot](#setup-bot)
- [🙏 Acknowledgments](#-acknowledgments)
- [📜 License](#-license)

## 🌟 Features

### Core Features
- **Multi-Provider Support** - Use OpenAI, DeepSeek, or any compatible API
- **Character Card V3** - Full support for Character Card V3 specification with lorebooks and assets
- **Intelligent Response Filter** - LLM-based system that decides when the AI should respond based on conversation context
- **Reply System** - AI can reply to specific Discord messages using `<REPLY:message_id>` syntax
- **Sleep Mode** - AI automatically sleeps after consecutive refusals and wakes up when mentioned
- **Configuration Presets** - Save and reuse AI configurations across different bots
- **Multiple API Connections** - Manage multiple API connections per server with different models and parameters

### Discord Features
- **Webhook Mode** - AI appears as a separate user with custom name and avatar
- **Bot Mode** - Traditional bot mode for simpler setups
- **30+ Slash Commands** - Full control over AI behavior and configuration
- **Response Regeneration** - Navigate through multiple AI responses with reactions (◀️ ▶️ 🔄)
- **Multi-Instance Support** - Run multiple AIs in the same server or channel


### Advanced Features
- **Tool Calling (Function Calling)** - AI can query Discord information (messages, users, channels, emojis, server stats) and manage persistent memory
- **Persistent Memory System** - AI can save and recall important information across conversations with token-based limits
- **Lorebook System [BETA]** - Context injection with decorators and conditional activation
- **CBS Processing** - Curly Braced Syntax support ({{char}}, {{user}}, {{random}}, etc.)
- **Thinking Models** - Full support for reasoning models
- **Text Processing** - Emoji filtering, regex patterns, custom formatting
- **Timing Control** - Engaged mode, cache thresholds, typing indicators
- **Backup/Restore** - Configuration backup and restore system

## ✨ What's New

This version is a complete rewrite with major improvements:

- **Multi-Provider Architecture** - No longer limited to Character.AI, now supports OpenAI, DeepSeek, and extensible to other providers!
- **Character Card V3** - Full implementation of the CCv3 specification including lorebooks, assets, decorators, and CBS
- **Tool Calling System** - AI can query Discord information (messages, users, channels, emojis, server stats) using function calling
- **Persistent Memory System** - AI can save and recall important information across conversations with independent memory per chat
- **Intelligent Response System** - LLM-based filter that analyzes conversation context to decide when to respond
- **Modern Message Pipeline** - Complete rewrite of message handling with better performance and reliability
- **Configuration System** - Hierarchical configuration with presets, YAML defaults, and hot-reload support
- **Reply System** - AI can now reply to specific messages in Discord
- **Sleep Mode** - AI conserves resources by sleeping when not needed
- **API Management** - Full control over LLM parameters (temperature, top_p, max_tokens, etc.)

## ⚠️ Warnings
1. **This is beta software** - Expect bugs and report them on our Discord
2. **API costs** - Using APIs incurs costs based on your usage
3. **Non-commercial use** - Strictly for experimental/educational purposes

## 🛠️ Setup Guide

### Prerequisites
- Discord developer account
- API key from a supported provider (OpenAI, DeepSeek, etc.)
- Python 3.11+ (for source version)
- Basic text editor (VS Code recommended)

### Discord Bot Creation
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create new application → Build → Bot
3. **Enable Privileged Intents**:
   - Presence Intent
   - Server Members Intent 
   - Message Content Intent
4. Copy bot token (store securely)
5. Invite bot to your server with these permissions:
   - Manage Webhooks
   - Send Messages
   - Read Message History
   - Add Reactions
   - Use Slash Commands

### Installation

**Requirements:**
- Python 3.11 or higher
- Git

#### Windows Users

1. **Install Python 3.11+**
   - Download from [python.org](https://www.python.org/downloads/)
   - **Important:** Check "Add Python to PATH" during installation

2. **Install Git**
   - Download from [git-scm.com](https://git-scm.com/download/win)
   - Use default installation options

3. **Install Hashi**
   ```bash
   # Open Command Prompt or PowerShell
   git clone https://github.com/LixxRarin/Hashi-AI-Discord.git
   cd Hashi-AI-Discord
   pip install -r requirements.txt
   python app.py
   ```

#### Linux Users

```bash
# Install Python 3.11+ (Ubuntu/Debian example)
sudo apt update && sudo apt install python3.11 python3-pip git

# Clone repository
git clone https://github.com/LixxRarin/Hashi-AI-Discord.git
cd Hashi-AI-Discord/

# Install dependencies (recommended use a virtual environment)
pip install -r requirements.txt

# Launch Hashi
python3.11 app.py
```

**Note:** On first run, `config.yml` will be auto-generated. Edit it with your Discord bot token before restarting.

### Configuration

Edit `config.yml` with your Discord token:

```yaml
Discord:
  token: "YOUR_DISCORD_TOKEN" # From developer portal
```

> The config.yml file is well documented and full of options!

### Setup Bot

#### 1. Create an API Connection

Use the `/new_api` command to create an API connection:

```
/new_api 
  connection_name: my-openai
  provider: openai
  api_key: sk-...
  model: gpt-4o-mini
  max_tokens: 1000
  temperature: 0.7
  [...]
```

You can create multiple API connections with different models and parameters.

#### 2. Setup AI in Channel

Use the `/setup` command to create an AI in a channel:

**Basic setup (uses default card):**

```
/setup
  channel: #your-channel
  api_connection: my-openai
  mode: bot
```

**Character Card Options** - Choose ONE of the following:

**Option 1: Use a registered card**
```
/setup
  channel: #your-channel
  api_connection: my-openai
  card_name: MyCharacter
  mode: webhook
```

**Option 2: Upload a card file directly**
```
/setup
  channel: #your-channel
  api_connection: my-openai
  card_attachment: [upload PNG/JSON/CHARX file]
  mode: webhook
```

**Option 3: Download from URL**
```
/setup
  channel: #your-channel
  api_connection: my-openai
  card_url: https://example.com/character.png
  mode: webhook
```

**Option 4: Use default card ;)**

If no card source is provided, the bot uses `character_cards/hashi.png` as the default character.

**About Character Cards (V3):**
- **Supported formats:** PNG (with embedded data), JSON, CHARX
- **Storage:** Cards are cached in the `character_cards/` folder
- **Specification:** Full Character Card V3 support
- **Sources:** Download from sites like [Chub AI](https://chub.ai/)

**Card Management:**
- Use `/import_card` to pre-register cards for reuse across multiple AIs
- Use `/list_cards` to see all registered cards in your server
- Registered cards can be applied to multiple AIs using `card_name`


#### 3. Configure AI Behavior (Optional)

Use the `/config_*` commands to customize your AI:

```
/config_timing ai_name:MyBot delay_for_generation:3.0
/config_display ai_name:MyBot send_message_line_by_line:true
/config_reply ai_name:MyBot enabled:True
```

You can also save configurations as presets and reuse them:

```
/preset_save ai_name:MyBot preset_name:fast_responder
/preset_apply preset_name:fast_responder ai_name:AnotherBot
```

## 🙏 Acknowledgments
- **[KarstSkarn](https://github.com/KarstSkarn)** for inspiration from [ChAIScrapper](https://github.com/KarstSkarn/ChAIScrapper)
- **[Hashi Character.AI Discord](https://github.com/LixxRarin/Hashi-CharacterAI-Discord)** (legacy project), and **[JpbmOfficial](https://github.com/JpbmOfficial)** for the feature request issues that inspired many of the new functionalities
- **[Character Card V3 Spec](https://github.com/kwaroran/character-card-spec-v3)** for the CCv3 specification

## 📜 License
MIT License - See [LICENSE](LICENSE) for details.