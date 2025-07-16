import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from config/.env
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Required environment variables
required_vars = [
    'BOT_TOKEN',
    'MEMBER_COUNT_CHANNEL_ID',
    'ONLINE_COUNT_CHANNEL_ID',
    'BAN_COUNT_CHANNEL_ID',
    'HEARTBEAT_CHANNEL_ID',
    'STATS_CHANNEL_ID'  # Add stats channel ID
]

# Check for missing environment variables
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Export config dictionary
config = {
    'BOT_TOKEN': os.getenv('BOT_TOKEN'),
    'MEMBER_COUNT_CHANNEL_ID': int(os.getenv('MEMBER_COUNT_CHANNEL_ID')),
    'ONLINE_COUNT_CHANNEL_ID': int(os.getenv('ONLINE_COUNT_CHANNEL_ID')),
    'BAN_COUNT_CHANNEL_ID': int(os.getenv('BAN_COUNT_CHANNEL_ID')),
    'HEARTBEAT_CHANNEL_ID': int(os.getenv('HEARTBEAT_CHANNEL_ID')),
    'STATS_CHANNEL_ID': int(os.getenv('STATS_CHANNEL_ID'))  # Add stats channel ID
} 