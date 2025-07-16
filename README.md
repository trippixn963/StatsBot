![StatsBot Banner](https://raw.githubusercontent.com/trippixn963/StatsBot/main/images/BANNER.gif)

# StatsBot 🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Discord](https://img.shields.io/badge/Discord-Syria-7289DA?logo=discord)](https://discord.gg/syria)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/Status-Stable-green)]()

A fully automated Discord statistics bot that tracks server activity and provides real-time updates through channel names and detailed reports. Originally created for [discord.gg/syria](https://discord.gg/syria).

> ⚠️ **DISCLAIMER**: This is a "take as is" project. No support, updates, or help will be provided. Use at your own discretion.

## Features 🚀

- **Automated Channel Statistics** 📊
  - Member count updates
  - Online member tracking
  - Ban count monitoring
  - Rate-limit aware with exponential backoff

- **Daily Statistics Reports** 📈
  - Sent automatically at 12 AM EST
  - Detailed member activity
  - Server growth metrics
  - Moderation activity summary

- **Real-time Monitoring** 🔍
  - Hourly heartbeat messages
  - System performance metrics
  - Recent member activity tracking
  - Log monitoring and reporting

## Project Structure 📁

```
StatsBot/
├── config/           # Configuration files and environment variables
├── data/            # JSON data storage for statistics
├── logs/            # Daily rotating logs
├── src/             # Source code
│   ├── services/    # Core services
│   └── utils/       # Utility functions
├── main.py          # Application entry point
└── requirements.txt # Project dependencies
```

## Setup ⚙️

1. Clone the repository
```bash
git clone https://github.com/yourusername/StatsBot.git
cd StatsBot
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Configure environment variables in `config/.env`:
```env
BOT_TOKEN=your_bot_token
MEMBER_COUNT_CHANNEL_ID=channel_id
ONLINE_COUNT_CHANNEL_ID=channel_id
BAN_COUNT_CHANNEL_ID=channel_id
HEARTBEAT_CHANNEL_ID=channel_id
STATS_CHANNEL_ID=channel_id
```

4. Run the bot
```bash
python main.py
```

## Environment Variables 🔐

| Variable | Description |
|----------|-------------|
| BOT_TOKEN | Your Discord bot token |
| MEMBER_COUNT_CHANNEL_ID | Channel to display member count |
| ONLINE_COUNT_CHANNEL_ID | Channel to display online count |
| BAN_COUNT_CHANNEL_ID | Channel to display ban count |
| HEARTBEAT_CHANNEL_ID | Channel for heartbeat messages |
| STATS_CHANNEL_ID | Channel for daily statistics |

## Features in Detail ✨

### Channel Statistics
- Updates channel names to reflect current server statistics
- Implements intelligent rate limiting
- Uses exponential backoff for rate limit handling

### Daily Statistics
- Automatically generates daily reports
- Tracks member joins and leaves
- Monitors server growth trends
- Provides moderation activity summary

### Heartbeat Monitoring
- Hourly status updates
- System performance metrics
- Recent member activity
- Log monitoring

## Logging System 📝

- Daily rotating log files
- Separate error logging
- JSON-formatted logs for analysis
- Rich console output

## Important Notice ⚠️

This bot is provided as-is without any warranty or support. It was specifically created for [discord.gg/syria](https://discord.gg/syria) and is being shared for reference purposes only. No maintenance, updates, or assistance will be provided.

## License

[MIT License](LICENSE) © 2025 John 