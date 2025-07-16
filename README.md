# StatsBot

A fully automated Discord statistics bot that tracks server activity and provides real-time updates through channel names and detailed reports.

## Features

- **Automated Channel Statistics**
  - Member count updates
  - Online member tracking
  - Ban count monitoring
  - Rate-limit aware with exponential backoff

- **Daily Statistics Reports**
  - Sent automatically at 12 AM EST
  - Detailed member activity
  - Server growth metrics
  - Moderation activity summary

- **Real-time Monitoring**
  - Hourly heartbeat messages
  - System performance metrics
  - Recent member activity tracking
  - Log monitoring and reporting

## Project Structure

```
StatsBot/
├── config/           # Configuration files and environment variables
├── data/            # JSON data storage for statistics
├── logs/            # Daily rotating logs (errors, general logs, JSON logs)
├── src/             # Source code
│   ├── services/    # Core services (monitoring, stats, presence)
│   └── utils/       # Utility functions and helpers
├── main.py          # Application entry point
└── requirements.txt # Project dependencies
```

## Setup

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

## Environment Variables

| Variable | Description |
|----------|-------------|
| BOT_TOKEN | Your Discord bot token |
| MEMBER_COUNT_CHANNEL_ID | Channel to display member count |
| ONLINE_COUNT_CHANNEL_ID | Channel to display online count |
| BAN_COUNT_CHANNEL_ID | Channel to display ban count |
| HEARTBEAT_CHANNEL_ID | Channel for heartbeat messages |
| STATS_CHANNEL_ID | Channel for daily statistics |

## Features in Detail

### Channel Statistics
- Updates channel names to reflect current server statistics
- Implements intelligent rate limiting to avoid Discord API restrictions
- Uses exponential backoff for rate limit handling

### Daily Statistics
- Automatically generates comprehensive daily reports
- Tracks member joins and leaves
- Monitors server growth trends
- Provides moderation activity summary

### Heartbeat Monitoring
- Hourly status updates
- System performance metrics
- Recent member activity
- Log monitoring

## Logging

The bot uses a sophisticated logging system with:
- Daily rotating log files
- Separate error logging
- JSON-formatted logs for analysis
- Rich console output

## Contributing

Feel free to submit issues and enhancement requests!

## License

[MIT License](LICENSE) 