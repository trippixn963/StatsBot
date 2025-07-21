"""
Discord Webhook Logging Service

Provides comprehensive webhook-based logging for Discord bots with features including:
- Multi-webhook support with level-based routing
- Rate limiting and queue management
- Circuit breaker pattern for reliability
- Message formatting and templating
- Security and privacy features
- Performance monitoring integration
"""

import asyncio
import aiohttp
import json
import time
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import traceback
from urllib.parse import urlparse
import hashlib

# Import existing utilities
from src.utils.tree_log import log_perfect_tree_section, log_error_with_traceback


class WebhookLogLevel(Enum):
    """Log levels for webhook routing."""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class WebhookStatus(Enum):
    """Webhook health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded" 
    FAILED = "failed"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class WebhookConfig:
    """Configuration for a single webhook."""
    url: str
    name: str = "default"
    min_level: WebhookLogLevel = WebhookLogLevel.INFO
    max_retries: int = 3
    timeout: float = 10.0
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate webhook configuration."""
        if not self.url or not self.url.startswith('https://discord.com/api/webhooks/'):
            raise ValueError(f"Invalid Discord webhook URL: {self.url}")
        
        # Mask URL for logging
        self.masked_url = self._mask_webhook_url()
    
    def _mask_webhook_url(self) -> str:
        """Mask sensitive parts of webhook URL."""
        try:
            parts = self.url.split('/')
            if len(parts) >= 2:
                token = parts[-1]
                webhook_id = parts[-2]
                return f"https://discord.com/api/webhooks/{webhook_id}/***"
            return "***masked***"
        except:
            return "***masked***"


@dataclass
class QueuedMessage:
    """Queued webhook message."""
    content: str
    webhook_name: str
    level: WebhookLogLevel
    timestamp: float
    priority: int = 0  # Higher = more priority
    retries: int = 0
    message_id: str = field(default_factory=lambda: str(time.time()))


class CircuitBreaker:
    """Circuit breaker for webhook reliability."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 300.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half_open
    
    def can_execute(self) -> bool:
        """Check if operation can be executed."""
        if self.state == "closed":
            return True
        elif self.state == "open":
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half_open"
                return True
            return False
        else:  # half_open
            return True
    
    def record_success(self):
        """Record successful operation."""
        self.failure_count = 0
        self.state = "closed"
    
    def record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"


class RateLimiter:
    """Discord API compliant rate limiter."""
    
    def __init__(self, requests_per_second: float = 5.0, burst_size: int = 10):
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_update = time.time()
        self.request_times = deque(maxlen=100)
    
    async def acquire(self) -> bool:
        """Acquire rate limit permission."""
        now = time.time()
        
        # Refill tokens
        time_passed = now - self.last_update
        self.tokens = min(self.burst_size, self.tokens + time_passed * self.requests_per_second)
        self.last_update = now
        
        if self.tokens >= 1:
            self.tokens -= 1
            self.request_times.append(now)
            return True
        
        return False
    
    def get_wait_time(self) -> float:
        """Get time to wait before next request."""
        if self.tokens >= 1:
            return 0
        return (1 - self.tokens) / self.requests_per_second


class MessageFormatter:
    """Format log messages for Discord webhooks."""
    
    def __init__(self):
        self.templates = self._load_default_templates()
        self.pii_patterns = [
            (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL]'),
            (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '[SSN]'),
            (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '[CARD]'),
            (re.compile(r'token["\s:=]+[A-Za-z0-9._-]+', re.IGNORECASE), 'token="[REDACTED]"'),
            (re.compile(r'password["\s:=]+[^\s"]+', re.IGNORECASE), 'password="[REDACTED]"'),
            (re.compile(r'secret["\s:=]+[^\s"]+', re.IGNORECASE), 'secret="[REDACTED]"'),
        ]
    
    def _load_default_templates(self) -> Dict[str, str]:
        """Load default message templates."""
        return {
            'error': {
                'title': '❌ Error Alert',
                'color': 0xFF0000,
                'template': '**{level}** | {timestamp}\n```\n{message}\n```'
            },
            'warning': {
                'title': '⚠️ Warning',
                'color': 0xFFA500,
                'template': '**{level}** | {timestamp}\n{message}'
            },
            'info': {
                'title': 'ℹ️ Information',
                'color': 0x0099FF,
                'template': '**{level}** | {timestamp}\n{message}'
            },
            'critical': {
                'title': '🔥 Critical Alert',
                'color': 0x8B0000,
                'template': '**{level}** | {timestamp}\n```\n{message}\n```\n<@&ADMIN_ROLE_ID>'
            },
            'heartbeat': {
                'title': '💓 Bot Status',
                'color': 0x00FF00,
                'template': '**System Health** | {timestamp}\n{message}'
            },
            'member_event': {
                'title': '👥 Member Event',
                'color': 0x7289DA,
                'template': '**{event_type}** | {timestamp}\n{message}'
            },
            'performance': {
                'title': '📊 Performance Alert',
                'color': 0xFF8C00,
                'template': '**Performance** | {timestamp}\n{message}'
            }
        }
    
    def sanitize_content(self, content: str) -> str:
        """Remove PII and sensitive information."""
        for pattern, replacement in self.pii_patterns:
            content = pattern.sub(replacement, content)
        return content
    
    def format_message(self, level: WebhookLogLevel, message: str, 
                      template_type: str = None, **kwargs) -> Dict[str, Any]:
        """Format message for Discord webhook."""
        # Determine template type based on level if not specified
        if not template_type:
            level_map = {
                WebhookLogLevel.DEBUG: 'info',
                WebhookLogLevel.INFO: 'info', 
                WebhookLogLevel.WARNING: 'warning',
                WebhookLogLevel.ERROR: 'error',
                WebhookLogLevel.CRITICAL: 'critical'
            }
            template_type = level_map.get(level, 'info')
        
        template = self.templates.get(template_type, self.templates['info'])
        
        # Sanitize message content
        clean_message = self.sanitize_content(message)
        
        # Format timestamp
        timestamp = kwargs.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S EST'))
        
        # Format content
        formatted_content = template['template'].format(
            level=level.name,
            message=clean_message,
            timestamp=timestamp,
            **kwargs
        )
        
        # Create embed payload
        embed = {
            'title': template['title'],
            'description': formatted_content[:2048],  # Discord limit
            'color': template['color'],
            'timestamp': datetime.utcnow().isoformat(),
            'footer': {
                'text': f'StatsBot • {level.name}'
            }
        }
        
        return {
            'embeds': [embed]
        }


class WebhookManager:
    """Manages Discord webhook delivery with reliability features."""
    
    def __init__(self):
        self.webhooks: Dict[str, WebhookConfig] = {}
        self.message_queue = asyncio.Queue(maxsize=1000)
        self.rate_limiters: Dict[str, RateLimiter] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.formatter = MessageFormatter()
        self.session: Optional[aiohttp.ClientSession] = None
        self.worker_task: Optional[asyncio.Task] = None
        self.running = False
        self.stats = {
            'messages_sent': 0,
            'messages_failed': 0,
            'webhooks_failed': 0,
            'queue_size': 0,
            'last_delivery': None
        }
    
    def add_webhook(self, config: WebhookConfig):
        """Add webhook configuration."""
        self.webhooks[config.name] = config
        self.rate_limiters[config.name] = RateLimiter()
        self.circuit_breakers[config.name] = CircuitBreaker()
        
        log_perfect_tree_section(
            "Webhook Added",
            [
                ("name", config.name),
                ("url", config.masked_url),
                ("min_level", config.min_level.name),
                ("enabled", str(config.enabled))
            ],
            emoji="🔗"
        )
    
    def remove_webhook(self, name: str):
        """Remove webhook configuration."""
        if name in self.webhooks:
            del self.webhooks[name]
            del self.rate_limiters[name]
            del self.circuit_breakers[name]
            
            log_perfect_tree_section(
                "Webhook Removed",
                [("name", name)],
                emoji="🗑️"
            )
    
    async def start(self):
        """Start webhook delivery system."""
        if self.running:
            return
        
        self.running = True
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10)
        )
        
        self.worker_task = asyncio.create_task(self._worker_loop())
        
        log_perfect_tree_section(
            "Webhook Manager",
            [
                ("status", "Started"),
                ("webhooks", str(len(self.webhooks))),
                ("queue_size", str(self.message_queue.qsize()))
            ],
            emoji="🚀"
        )
    
    async def stop(self):
        """Stop webhook delivery system."""
        self.running = False
        
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        
        if self.session:
            await self.session.close()
        
        log_perfect_tree_section(
            "Webhook Manager",
            [("status", "Stopped")],
            emoji="🛑"
        )
    
    async def send_log(self, level: WebhookLogLevel, message: str, 
                      template_type: str = None, priority: int = 0, **kwargs):
        """Send log message to appropriate webhooks."""
        if not self.running:
            return
        
        # Find matching webhooks
        matching_webhooks = []
        for name, config in self.webhooks.items():
            if (config.enabled and 
                level.value >= config.min_level.value and 
                self.circuit_breakers[name].can_execute()):
                matching_webhooks.append(name)
        
        if not matching_webhooks:
            return
        
        # Format message
        try:
            payload = self.formatter.format_message(level, message, template_type, **kwargs)
            content = json.dumps(payload)
        except Exception as e:
            log_error_with_traceback("Failed to format webhook message", e)
            return
        
        # Queue messages for each webhook
        for webhook_name in matching_webhooks:
            queued_msg = QueuedMessage(
                content=content,
                webhook_name=webhook_name,
                level=level,
                timestamp=time.time(),
                priority=priority
            )
            
            try:
                self.message_queue.put_nowait(queued_msg)
                self.stats['queue_size'] = self.message_queue.qsize()
            except asyncio.QueueFull:
                # Drop oldest non-critical message
                try:
                    old_msg = self.message_queue.get_nowait()
                    if old_msg.level != WebhookLogLevel.CRITICAL:
                        self.message_queue.put_nowait(queued_msg)
                    else:
                        self.message_queue.put_nowait(old_msg)  # Put critical back
                except asyncio.QueueEmpty:
                    pass
    
    async def _worker_loop(self):
        """Main worker loop for processing webhook messages."""
        while self.running:
            try:
                # Get message with timeout
                try:
                    message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                # Update queue size
                self.stats['queue_size'] = self.message_queue.qsize()
                
                # Process message
                success = await self._deliver_message(message)
                
                if success:
                    self.stats['messages_sent'] += 1
                    self.stats['last_delivery'] = time.time()
                else:
                    self.stats['messages_failed'] += 1
                    
                    # Retry logic
                    if message.retries < self.webhooks[message.webhook_name].max_retries:
                        message.retries += 1
                        
                        # Exponential backoff
                        delay = min(300, 2 ** message.retries)
                        await asyncio.sleep(delay)
                        
                        try:
                            self.message_queue.put_nowait(message)
                        except asyncio.QueueFull:
                            pass  # Drop if queue full on retry
                
            except Exception as e:
                log_error_with_traceback("Error in webhook worker loop", e)
                await asyncio.sleep(5)
    
    async def _deliver_message(self, message: QueuedMessage) -> bool:
        """Deliver single message to webhook."""
        webhook_config = self.webhooks.get(message.webhook_name)
        if not webhook_config:
            return False
        
        rate_limiter = self.rate_limiters[message.webhook_name]
        circuit_breaker = self.circuit_breakers[message.webhook_name]
        
        # Check circuit breaker
        if not circuit_breaker.can_execute():
            return False
        
        # Rate limiting
        if not await rate_limiter.acquire():
            wait_time = rate_limiter.get_wait_time()
            if wait_time > 0:
                await asyncio.sleep(min(wait_time, 60))  # Max 1 minute wait
                if not await rate_limiter.acquire():
                    return False
        
        # Send message
        try:
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'StatsBot/1.0'
            }
            
            async with self.session.post(
                webhook_config.url,
                data=message.content,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=webhook_config.timeout)
            ) as response:
                
                if response.status == 200:
                    circuit_breaker.record_success()
                    return True
                elif response.status == 429:  # Rate limited
                    retry_after = float(response.headers.get('Retry-After', 60))
                    await asyncio.sleep(min(retry_after, 300))
                    return False
                else:
                    circuit_breaker.record_failure()
                    return False
                    
        except Exception as e:
            circuit_breaker.record_failure()
            log_error_with_traceback(f"Failed to deliver webhook message to {webhook_config.name}", e)
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get webhook system status."""
        webhook_statuses = {}
        for name, breaker in self.circuit_breakers.items():
            if breaker.state == "open":
                status = WebhookStatus.CIRCUIT_OPEN
            elif breaker.state == "half_open":
                status = WebhookStatus.DEGRADED
            else:
                status = WebhookStatus.HEALTHY
            
            webhook_statuses[name] = {
                'status': status.value,
                'failure_count': breaker.failure_count,
                'enabled': self.webhooks[name].enabled
            }
        
        return {
            'running': self.running,
            'webhooks': webhook_statuses,
            'stats': self.stats.copy(),
            'queue_size': self.message_queue.qsize()
        }


class WebhookLoggingService:
    """Main webhook logging service."""
    
    def __init__(self, bot_config: dict = None):
        self.manager = WebhookManager()
        self.config = bot_config or {}
        self.enabled = False
    
    def load_config(self, config: dict):
        """Load webhook configuration."""
        webhook_configs = config.get('webhooks', {})
        
        for name, webhook_data in webhook_configs.items():
            try:
                webhook_config = WebhookConfig(
                    url=webhook_data['url'],
                    name=name,
                    min_level=WebhookLogLevel[webhook_data.get('min_level', 'INFO')],
                    max_retries=webhook_data.get('max_retries', 3),
                    timeout=webhook_data.get('timeout', 10.0),
                    enabled=webhook_data.get('enabled', True),
                    tags=webhook_data.get('tags', [])
                )
                self.manager.add_webhook(webhook_config)
            except Exception as e:
                log_error_with_traceback(f"Failed to load webhook config for {name}", e)
        
        self.enabled = len(self.manager.webhooks) > 0
    
    async def start(self):
        """Start webhook logging service."""
        if self.enabled:
            await self.manager.start()
    
    async def stop(self):
        """Stop webhook logging service."""
        await self.manager.stop()
    
    # Convenience methods for different log types
    async def log_error(self, message: str, error: Exception = None, **kwargs):
        """Log error message."""
        if error:
            message = f"{message}\n\nError: {str(error)}\n\nTraceback:\n{traceback.format_exc()}"
        await self.manager.send_log(WebhookLogLevel.ERROR, message, 'error', priority=3, **kwargs)
    
    async def log_critical(self, message: str, **kwargs):
        """Log critical message."""
        await self.manager.send_log(WebhookLogLevel.CRITICAL, message, 'critical', priority=5, **kwargs)
    
    async def log_warning(self, message: str, **kwargs):
        """Log warning message."""
        await self.manager.send_log(WebhookLogLevel.WARNING, message, 'warning', priority=2, **kwargs)
    
    async def log_info(self, message: str, **kwargs):
        """Log info message."""
        await self.manager.send_log(WebhookLogLevel.INFO, message, 'info', priority=1, **kwargs)
    
    async def log_heartbeat(self, data: dict, **kwargs):
        """Log heartbeat/status message."""
        message = "\n".join([f"**{k.title()}:** {v}" for k, v in data.items()])
        await self.manager.send_log(WebhookLogLevel.INFO, message, 'heartbeat', priority=1, **kwargs)
    
    async def log_member_event(self, event_type: str, member_data: dict, **kwargs):
        """Log member event."""
        message = f"**User:** {member_data.get('username', 'Unknown')}\n"
        message += f"**ID:** {member_data.get('id', 'Unknown')}\n"
        message += f"**Event:** {event_type}"
        
        await self.manager.send_log(
            WebhookLogLevel.INFO, 
            message, 
            'member_event', 
            priority=1,
            event_type=event_type,
            **kwargs
        )
    
    async def log_performance_alert(self, metric: str, value: Any, threshold: Any, **kwargs):
        """Log performance alert."""
        message = f"**Metric:** {metric}\n**Current:** {value}\n**Threshold:** {threshold}"
        await self.manager.send_log(WebhookLogLevel.WARNING, message, 'performance', priority=3, **kwargs)
    
    def get_status(self) -> Dict[str, Any]:
        """Get webhook logging status."""
        return {
            'enabled': self.enabled,
            'manager_status': self.manager.get_status()
        } 