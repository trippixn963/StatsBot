# Discord Webhook Logging

This module provides comprehensive Discord webhook logging capabilities for StatsBot, enabling real-time monitoring of bot operations, errors, performance metrics, and system events directly within Discord channels.

## Features

- **Multiple Webhook Endpoints**: Configure different webhooks for different log levels and event types
- **Structured Message Formatting**: Well-formatted messages with rich embeds and context
- **Log Level Filtering**: Route different log levels to different channels
- **Rate Limiting and Batching**: Respect Discord's API limits with intelligent batching
- **Error Handling and Fallback**: Resilient logging with circuit breaker pattern
- **Security and Privacy**: Configurable PII masking and data sanitization
- **Integration with Existing Systems**: Seamless integration with StatsBot's logging

## Quick Start

### 1. Configure Webhook URLs

Add the following environment variables to your `.env` file:

```env
# Primary webhook URLs
WEBHOOK_ERROR_URL=https://discord.com/api/webhooks/123/abc
WEBHOOK_INFO_URL=https://discord.com/api/webhooks/456/def
WEBHOOK_PERFORMANCE_URL=https://discord.com/api/webhooks/789/ghi
WEBHOOK_MEMBER_EVENTS_URL=https://discord.com/api/webhooks/012/jkl

# Optional configuration
WEBHOOK_USE_EMBEDS=true
WEBHOOK_MASK_USER_IDS=false
```

### 2. Initialize Webhook Logging

```python
from src.utils.webhook_logging import setup_webhook_logging

# Initialize webhook logging (loads config from environment)
webhook_manager = setup_webhook_logging()

# Start the webhook manager
await webhook_manager.start()
```

### 3. Send Logs to Webhooks

```python
from src.utils.webhook_logging import get_webhook_manager
from src.utils.webhook_logging.config import LogLevel

# Get the webhook manager
webhook_manager = get_webhook_manager()

# Send a log message
await webhook_manager.send_log(
    LogLevel.INFO,
    "Bot started successfully",
    version="1.0.0",
    guild_count=10
)

# Send an error
try:
    # Some code that might fail
    result = 1 / 0
except Exception as e:
    await webhook_manager.send_error(
        e,
        component="example",
        operation="division"
    )
```

### 4. Integrate with Existing Logging

```python
from src.utils.webhook_logging.integration import (
    integrate_with_tree_log,
    integrate_with_performance_monitor,
    integrate_with_member_events
)

# Integrate with tree_log.py
integrate_with_tree_log()

# Integrate with performance monitoring
integrate_with_performance_monitor()

# Integrate with member events
integrate_with_member_events(bot)
```

## Configuration Options

### WebhookConfig

```python
@dataclass
class WebhookConfig:
    # Primary webhook URLs
    error_webhook_url: Optional[str] = None
    info_webhook_url: Optional[str] = None
    performance_webhook_url: Optional[str] = None
    member_events_webhook_url: Optional[str] = None
    
    # Rate limiting settings
    max_requests_per_minute: int = 30
    batch_size: int = 5
    batch_timeout_seconds: float = 10.0
    
    # Message formatting
    use_embeds: bool = True
    include_timestamps: bool = True
    include_bot_info: bool = True
    
    # Privacy settings
    mask_user_ids: bool = False
    include_stack_traces: bool = True
    max_message_length: int = 2000
```

## Message Types

### Log Messages

Log messages include:
- Log level (INFO, WARNING, ERROR, etc.)
- Message text
- Additional context (component, timestamp, etc.)
- Stack trace for errors (if available)

### Performance Alerts

Performance alerts include:
- Metric name (e.g., "memory_usage")
- Current value
- Threshold value
- Severity ratio
- Additional context

### Member Events

Member events include:
- Event type (join, leave, ban, etc.)
- Member ID (optionally masked)
- Username
- Guild information
- Additional context

## Advanced Usage

### Custom Message Formatting

```python
from src.utils.webhook_logging import WebhookConfig, MessageFormatter

# Create custom config
config = WebhookConfig(
    error_webhook_url="https://discord.com/api/webhooks/123/abc",
    use_embeds=True,
    include_timestamps=True
)

# Create custom formatter
formatter = MessageFormatter(config)

# Format custom message
message = formatter.format_log_message(
    LogLevel.INFO,
    "Custom message",
    component="example"
)
```

### Circuit Breaker Pattern

The webhook client implements a circuit breaker pattern to handle webhook failures:

1. After multiple consecutive failures, the circuit "opens"
2. While open, requests are skipped without attempting delivery
3. After a cooldown period, the circuit "resets" and tries again
4. If successful, the circuit "closes" and normal operation resumes

This prevents cascading failures and respects Discord's rate limits.

## Example

See `examples/webhook_logging_example.py` for a complete example of using the webhook logging system.

## Integration with StatsBot

The webhook logging system integrates with StatsBot's existing logging infrastructure:

- **tree_log.py**: Logs sent through tree_log functions are also sent to webhooks
- **performance.py**: Performance alerts are sent to webhooks
- **Member Events**: Member join/leave/ban events are sent to webhooks

## Best Practices

1. **Use Different Webhooks**: Create separate webhooks for different log levels and event types
2. **Configure Privacy Settings**: Use `mask_user_ids` to protect user privacy
3. **Monitor Rate Limits**: Adjust `max_requests_per_minute` based on your Discord server's limits
4. **Use Rich Embeds**: Enable `use_embeds` for better message formatting
5. **Include Context**: Add relevant context to log messages for better debugging