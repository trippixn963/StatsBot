# Discord Webhook Logging Design Document

## Overview

The Discord Webhook Logging feature integrates seamlessly with StatsBot's existing logging infrastructure to provide real-time monitoring capabilities through Discord webhooks. This system extends the current `tree_log` utility and performance monitoring to deliver structured, actionable alerts and information directly to Discord channels.

## Architecture

### Core Components

```
src/utils/webhook_logging/
├── __init__.py
├── webhook_manager.py      # Main webhook management
├── message_formatter.py    # Message formatting and templating
├── rate_limiter.py        # Rate limiting and batching
├── config.py              # Webhook configuration
└── filters.py             # Log filtering and routing
```

### Integration Points

1. **Existing Logging System**: Extends `src/utils/tree_log.py`
2. **Performance Monitor**: Integrates with `src/utils/performance.py`
3. **Configuration System**: Uses existing environment configuration
4. **Error Handling**: Leverages existing error handling patterns

## Components and Interfaces

### WebhookManager

```python
class WebhookManager:
    """
    Central manager for Discord webhook logging operations.
    
    Handles webhook registration, message routing, rate limiting,
    and error recovery for all webhook operations.
    """
    
    def __init__(self, config: WebhookConfig):
        self.config = config
        self.webhooks: Dict[str, WebhookClient] = {}
        self.rate_limiter = RateLimiter()
        self.message_formatter = MessageFormatter()
        self.filters = LogFilters()
    
    async def send_log(self, level: LogLevel, message: str, **context) -> None:
        """Send log message to appropriate webhooks."""
        
    async def send_performance_alert(self, metric: PerformanceMetric) -> None:
        """Send performance monitoring alerts."""
        
    async def send_system_status(self, status: SystemStatus) -> None:
        """Send system status updates."""
```

### MessageFormatter

```python
class MessageFormatter:
    """
    Formats log messages for Discord webhook delivery.
    
    Supports both plain text and rich embed formatting with
    customizable templates and variable substitution.
    """
    
    def format_log_message(self, level: LogLevel, message: str, **context) -> WebhookMessage:
        """Format standard log message."""
        
    def format_error_message(self, error: Exception, context: Dict) -> WebhookMessage:
        """Format error messages with stack traces."""
        
    def format_performance_alert(self, metric: PerformanceMetric) -> WebhookMessage:
        """Format performance monitoring alerts."""
        
    def format_member_event(self, event_type: str, member_data: Dict) -> WebhookMessage:
        """Format member join/leave/ban events."""
```

### RateLimiter

```python
class RateLimiter:
    """
    Manages rate limiting and message batching for webhook delivery.
    
    Implements Discord's rate limiting requirements with exponential
    backoff and intelligent batching to prevent API abuse.
    """
    
    def __init__(self, max_requests_per_minute: int = 30):
        self.max_requests = max_requests_per_minute
        self.request_queue: asyncio.Queue = asyncio.Queue()
        self.batch_processor = BatchProcessor()
    
    async def queue_message(self, webhook_url: str, message: WebhookMessage) -> None:
        """Queue message for rate-limited delivery."""
        
    async def process_queue(self) -> None:
        """Process queued messages with rate limiting."""
```

## Data Models

### WebhookConfig

```python
@dataclass
class WebhookConfig:
    """Configuration for webhook logging system."""
    
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

### WebhookMessage

```python
@dataclass
class WebhookMessage:
    """Represents a formatted webhook message."""
    
    content: Optional[str] = None
    embeds: List[Dict[str, Any]] = field(default_factory=list)
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to Discord webhook payload."""
```

### LogLevel Routing

```python
class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

WEBHOOK_ROUTING = {
    LogLevel.CRITICAL: ["error_webhook_url", "info_webhook_url"],
    LogLevel.ERROR: ["error_webhook_url"],
    LogLevel.WARNING: ["error_webhook_url"],
    LogLevel.INFO: ["info_webhook_url"],
    LogLevel.DEBUG: []  # Only if explicitly enabled
}
```

## Error Handling

### Webhook Delivery Failures

1. **Retry Logic**: Exponential backoff with jitter (1s, 2s, 4s, 8s, 16s max)
2. **Circuit Breaker**: Temporarily disable failing webhooks
3. **Fallback**: Continue with file logging if all webhooks fail
4. **Recovery**: Automatic re-enable of webhooks after cooldown period

### Rate Limit Handling

1. **Proactive Limiting**: Stay under Discord's limits
2. **Backoff Strategy**: Respect Discord's retry-after headers
3. **Queue Management**: Drop oldest messages if queue becomes too large
4. **Priority System**: Critical errors bypass normal queuing

## Testing Strategy

### Unit Tests

- Message formatting with various log levels and contexts
- Rate limiting behavior under different load conditions
- Configuration validation and error handling
- Webhook client retry logic and circuit breaker functionality

### Integration Tests

- End-to-end webhook delivery with mock Discord API
- Integration with existing logging system
- Performance monitoring alert delivery
- Batch processing and queue management

### Performance Tests

- High-volume log message handling
- Memory usage under sustained webhook activity
- Rate limiting effectiveness
- Message formatting performance

## Security Considerations

### Data Privacy

- Configurable PII masking for user data
- Token and secret redaction from all log messages
- Optional user ID hashing for privacy compliance
- Configurable data retention for webhook logs

### Webhook Security

- Webhook URL validation and sanitization
- Secure storage of webhook configurations
- Rate limiting to prevent abuse
- Input validation for all webhook payloads

## Configuration Examples

### Environment Variables

```env
# Primary webhook URLs
WEBHOOK_ERROR_URL=https://discord.com/api/webhooks/123/abc
WEBHOOK_INFO_URL=https://discord.com/api/webhooks/456/def
WEBHOOK_PERFORMANCE_URL=https://discord.com/api/webhooks/789/ghi
WEBHOOK_MEMBER_EVENTS_URL=https://discord.com/api/webhooks/012/jkl

# Rate limiting
WEBHOOK_MAX_REQUESTS_PER_MINUTE=30
WEBHOOK_BATCH_SIZE=5
WEBHOOK_BATCH_TIMEOUT=10

# Message formatting
WEBHOOK_USE_EMBEDS=true
WEBHOOK_INCLUDE_TIMESTAMPS=true
WEBHOOK_MAX_MESSAGE_LENGTH=2000

# Privacy settings
WEBHOOK_MASK_USER_IDS=false
WEBHOOK_INCLUDE_STACK_TRACES=true
```

### Message Templates

```python
ERROR_TEMPLATE = {
    "embeds": [{
        "title": "🚨 Bot Error Alert",
        "color": 0xFF0000,
        "fields": [
            {"name": "Error Type", "value": "{error_type}", "inline": True},
            {"name": "Component", "value": "{component}", "inline": True},
            {"name": "Timestamp", "value": "{timestamp}", "inline": True},
            {"name": "Message", "value": "{message}", "inline": False},
            {"name": "Stack Trace", "value": "```{stack_trace}```", "inline": False}
        ],
        "footer": {"text": "StatsBot Error Monitor"}
    }]
}

PERFORMANCE_TEMPLATE = {
    "embeds": [{
        "title": "📊 Performance Alert",
        "color": 0xFFA500,
        "fields": [
            {"name": "Metric", "value": "{metric_name}", "inline": True},
            {"name": "Value", "value": "{metric_value}", "inline": True},
            {"name": "Threshold", "value": "{threshold}", "inline": True},
            {"name": "Details", "value": "{details}", "inline": False}
        ],
        "footer": {"text": "StatsBot Performance Monitor"}
    }]
}
```

## Implementation Phases

### Phase 1: Core Infrastructure
- WebhookManager and basic message sending
- Configuration system and environment integration
- Basic message formatting (plain text)

### Phase 2: Advanced Formatting
- Rich embed support with templates
- Variable substitution system
- Custom formatting for different log types

### Phase 3: Rate Limiting and Batching
- Intelligent rate limiting implementation
- Message batching and queue management
- Retry logic and error recovery

### Phase 4: Integration and Testing
- Integration with existing logging systems
- Performance monitoring integration
- Comprehensive testing and optimization

This design provides a robust, scalable webhook logging system that enhances StatsBot's monitoring capabilities while maintaining the high performance and reliability standards of the existing codebase.