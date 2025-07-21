"""
WebhookManager for Discord webhook logging.

This module provides the core webhook management functionality, handling
webhook registration, message routing, rate limiting, and error recovery.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Callable, Awaitable
import aiohttp
from datetime import datetime, timezone

from .config import WebhookConfig, LogLevel
from .message_formatter import MessageFormatter, WebhookMessage

logger = logging.getLogger("webhook_logging")

class WebhookClient:
    """
    Client for a single Discord webhook endpoint.
    
    Handles sending messages to a specific webhook URL with error handling,
    retries, and circuit breaking.
    """
    
    def __init__(self, webhook_url: str, session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize webhook client.
        
        Args:
            webhook_url: Discord webhook URL
            session: Optional aiohttp session to use
        """
        self.webhook_url = webhook_url
        self.session = session or aiohttp.ClientSession()
        self.created_session = session is None
        
        # Circuit breaker state
        self.consecutive_failures = 0
        self.circuit_open = False
        self.last_attempt = 0
        self.cooldown_period = 60  # seconds
        self.max_failures = 3
        
        # Success/failure tracking
        self.total_sent = 0
        self.total_failed = 0
        self.last_success = None
    
    async def send_message(self, message: WebhookMessage) -> bool:
        """
        Send a message to the webhook.
        
        Args:
            message: The webhook message to send
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Check circuit breaker
        if self.circuit_open:
            current_time = time.time()
            if current_time - self.last_attempt < self.cooldown_period:
                logger.debug(f"Circuit open for webhook {self.webhook_url}, skipping request")
                return False
            
            # Reset circuit breaker for retry
            logger.info(f"Resetting circuit breaker for webhook {self.webhook_url}")
            self.circuit_open = False
        
        # Update last attempt time
        self.last_attempt = time.time()
        
        try:
            # Convert message to payload
            payload = message.to_payload()
            
            # Send webhook request
            async with self.session.post(self.webhook_url, json=payload) as response:
                if response.status == 429:
                    # Handle rate limiting
                    retry_after = float(response.headers.get('Retry-After', '1'))
                    logger.warning(f"Rate limited by Discord, retry after {retry_after}s")
                    await asyncio.sleep(retry_after)
                    return await self.send_message(message)  # Retry after waiting
                
                elif response.status >= 400:
                    # Handle error response
                    error_text = await response.text()
                    logger.error(f"Webhook error {response.status}: {error_text}")
                    self._handle_failure()
                    return False
                
                else:
                    # Success
                    self._handle_success()
                    return True
                
        except Exception as e:
            logger.error(f"Webhook request failed: {str(e)}")
            self._handle_failure()
            return False
    
    def _handle_success(self):
        """Handle successful webhook delivery."""
        self.consecutive_failures = 0
        self.total_sent += 1
        self.last_success = datetime.now(timezone.utc)
    
    def _handle_failure(self):
        """Handle webhook delivery failure."""
        self.consecutive_failures += 1
        self.total_failed += 1
        
        # Open circuit breaker if too many failures
        if self.consecutive_failures >= self.max_failures:
            logger.warning(f"Circuit breaker opened for webhook {self.webhook_url} after {self.consecutive_failures} failures")
            self.circuit_open = True
    
    async def close(self):
        """Close the webhook client and clean up resources."""
        if self.created_session and not self.session.closed:
            await self.session.close()


class WebhookManager:
    """
    Central manager for Discord webhook logging operations.
    
    Handles webhook registration, message routing, rate limiting,
    and error recovery for all webhook operations.
    """
    
    def __init__(self, config: WebhookConfig):
        """
        Initialize webhook manager.
        
        Args:
            config: Webhook configuration
        """
        self.config = config
        self.webhooks: Dict[str, WebhookClient] = {}
        self.session = aiohttp.ClientSession()
        self.message_formatter = MessageFormatter(config)
        
        # Initialize webhooks
        self._initialize_webhooks()
        
        # Set up message queue for rate limiting
        self.message_queue = asyncio.Queue()
        self.queue_processor_task = None
        
        logger.info("WebhookManager initialized")
    
    def _initialize_webhooks(self):
        """Initialize webhook clients for all configured webhooks."""
        # Add all unique webhook URLs
        for url_attr in ['error_webhook_url', 'info_webhook_url', 
                         'performance_webhook_url', 'member_events_webhook_url']:
            url = getattr(self.config, url_attr, None)
            if url and url not in self.webhooks:
                self.webhooks[url] = WebhookClient(url, self.session)
                logger.debug(f"Initialized webhook client for {url_attr}: {url}")
    
    async def start(self):
        """Start the webhook manager and queue processor."""
        if self.queue_processor_task is None:
            self.queue_processor_task = asyncio.create_task(self._process_queue())
            logger.debug("Started webhook queue processor")
    
    async def stop(self):
        """Stop the webhook manager and clean up resources."""
        # Cancel queue processor
        if self.queue_processor_task:
            self.queue_processor_task.cancel()
            try:
                await self.queue_processor_task
            except asyncio.CancelledError:
                pass
            self.queue_processor_task = None
        
        # Close session
        await self.session.close()
        logger.debug("WebhookManager stopped")
    
    async def send_log(self, level: LogLevel, message: str, **context) -> None:
        """
        Send log message to appropriate webhooks.
        
        Args:
            level: Log level
            message: Log message
            **context: Additional context for the message
        """
        # Get webhooks for this log level
        webhook_urls = self.config.get_webhooks_for_level(level)
        if not webhook_urls:
            return
        
        # Format message
        webhook_message = self.message_formatter.format_log_message(level, message, **context)
        
        # Queue message for each webhook
        for url in webhook_urls:
            await self.message_queue.put((url, webhook_message))
    
    async def send_error(self, error: Exception, **context) -> None:
        """
        Send error message to error webhooks.
        
        Args:
            error: Exception to log
            **context: Additional context for the error
        """
        # Get error webhooks
        webhook_urls = self.config.get_webhooks_for_level(LogLevel.ERROR)
        if not webhook_urls:
            return
        
        # Format error message
        webhook_message = self.message_formatter.format_error_message(error, context)
        
        # Queue message for each webhook
        for url in webhook_urls:
            await self.message_queue.put((url, webhook_message))
    
    async def send_performance_alert(self, metric_name: str, value: float, 
                                    threshold: float, **context) -> None:
        """
        Send performance monitoring alert.
        
        Args:
            metric_name: Name of the performance metric
            value: Current metric value
            threshold: Threshold that triggered the alert
            **context: Additional context for the alert
        """
        # Use performance webhook if available, otherwise error webhook
        webhook_url = self.config.performance_webhook_url
        if not webhook_url:
            webhook_urls = self.config.get_webhooks_for_level(LogLevel.WARNING)
            if not webhook_urls:
                return
            webhook_url = webhook_urls[0]
        
        # Format performance alert
        webhook_message = self.message_formatter.format_performance_alert(
            metric_name, value, threshold, **context
        )
        
        # Queue message
        await self.message_queue.put((webhook_url, webhook_message))
    
    async def send_member_event(self, event_type: str, member_id: int, 
                               username: str, **context) -> None:
        """
        Send member event notification.
        
        Args:
            event_type: Type of event (join, leave, ban, etc.)
            member_id: Discord member ID
            username: Discord username
            **context: Additional context for the event
        """
        # Use member events webhook if available, otherwise info webhook
        webhook_url = self.config.member_events_webhook_url
        if not webhook_url:
            webhook_urls = self.config.get_webhooks_for_level(LogLevel.INFO)
            if not webhook_urls:
                return
            webhook_url = webhook_urls[0]
        
        # Format member event
        webhook_message = self.message_formatter.format_member_event(
            event_type, member_id, username, **context
        )
        
        # Queue message
        await self.message_queue.put((webhook_url, webhook_message))
    
    async def _process_queue(self):
        """Process the message queue with rate limiting."""
        try:
            while True:
                # Get next message from queue
                webhook_url, message = await self.message_queue.get()
                
                try:
                    # Get webhook client
                    webhook = self.webhooks.get(webhook_url)
                    if not webhook:
                        logger.warning(f"No webhook client for URL: {webhook_url}")
                        continue
                    
                    # Send message
                    success = await webhook.send_message(message)
                    if not success:
                        logger.warning(f"Failed to send webhook message to {webhook_url}")
                    
                    # Rate limiting - simple delay between requests
                    # In a more advanced implementation, this would use proper rate limiting
                    await asyncio.sleep(1.0 / (self.config.max_requests_per_minute / 60))
                    
                except Exception as e:
                    logger.error(f"Error processing webhook message: {str(e)}")
                
                finally:
                    # Mark task as done
                    self.message_queue.task_done()
                    
        except asyncio.CancelledError:
            logger.debug("Webhook queue processor cancelled")
            raise