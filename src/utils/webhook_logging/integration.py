"""
Integration with existing logging systems.

This module provides integration points between the webhook logging system
and StatsBot's existing logging infrastructure.
"""

import logging
import traceback
from typing import Optional, Dict, Any

from .config import WebhookConfig, LogLevel
from .webhook_manager import WebhookManager
from . import get_webhook_manager

# Setup logger
logger = logging.getLogger("webhook_logging")

def log_to_webhook(level: LogLevel, message: str, **context):
    """
    Log a message to webhook.
    
    Args:
        level: Log level
        message: Log message
        **context: Additional context for the message
    """
    try:
        # Get webhook manager
        webhook_manager = get_webhook_manager()
        
        # Send log asynchronously
        import asyncio
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(
            webhook_manager.send_log(level, message, **context),
            loop
        )
    except Exception as e:
        # Log error but don't propagate to avoid loops
        logger.error(f"Failed to send log to webhook: {str(e)}")

def log_error_to_webhook(error: Exception, **context):
    """
    Log an error to webhook.
    
    Args:
        error: Exception to log
        **context: Additional context for the error
    """
    try:
        # Get webhook manager
        webhook_manager = get_webhook_manager()
        
        # Send error asynchronously
        import asyncio
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(
            webhook_manager.send_error(error, **context),
            loop
        )
    except Exception as e:
        # Log error but don't propagate to avoid loops
        logger.error(f"Failed to send error to webhook: {str(e)}")

def log_performance_alert_to_webhook(metric_name: str, value: float, 
                                   threshold: float, **context):
    """
    Log a performance alert to webhook.
    
    Args:
        metric_name: Name of the performance metric
        value: Current metric value
        threshold: Threshold that triggered the alert
        **context: Additional context for the alert
    """
    try:
        # Get webhook manager
        webhook_manager = get_webhook_manager()
        
        # Send performance alert asynchronously
        import asyncio
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(
            webhook_manager.send_performance_alert(metric_name, value, threshold, **context),
            loop
        )
    except Exception as e:
        # Log error but don't propagate to avoid loops
        logger.error(f"Failed to send performance alert to webhook: {str(e)}")

def log_member_event_to_webhook(event_type: str, member_id: int, 
                              username: str, **context):
    """
    Log a member event to webhook.
    
    Args:
        event_type: Type of event (join, leave, ban, etc.)
        member_id: Discord member ID
        username: Discord username
        **context: Additional context for the event
    """
    try:
        # Get webhook manager
        webhook_manager = get_webhook_manager()
        
        # Send member event asynchronously
        import asyncio
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(
            webhook_manager.send_member_event(event_type, member_id, username, **context),
            loop
        )
    except Exception as e:
        # Log error but don't propagate to avoid loops
        logger.error(f"Failed to send member event to webhook: {str(e)}")

# Integration with tree_log.py
def integrate_with_tree_log():
    """
    Integrate webhook logging with tree_log.py.
    
    This function patches the tree_log functions to also send logs to webhooks.
    """
    try:
        from src.utils.tree_log import (
            log_perfect_tree_section,
            log_error_with_traceback,
            log_run_header,
            log_run_end
        )
        
        # Store original functions
        original_log_perfect_tree_section = log_perfect_tree_section
        original_log_error_with_traceback = log_error_with_traceback
        original_log_run_header = log_run_header
        original_log_run_end = log_run_end
        
        # Patch log_perfect_tree_section
        def patched_log_perfect_tree_section(title, items, emoji="", level="INFO"):
            # Call original function
            result = original_log_perfect_tree_section(title, items, emoji, level)
            
            # Map level string to LogLevel enum
            log_level = LogLevel.INFO
            if level == "WARNING":
                log_level = LogLevel.WARNING
            elif level == "ERROR":
                log_level = LogLevel.ERROR
            elif level == "CRITICAL":
                log_level = LogLevel.CRITICAL
            elif level == "DEBUG":
                log_level = LogLevel.DEBUG
            
            # Convert items to context dict
            context = {key: value for key, value in items}
            
            # Send to webhook
            log_to_webhook(log_level, f"{emoji} {title}", **context)
            
            return result
        
        # Patch log_error_with_traceback
        def patched_log_error_with_traceback(message, error, level="ERROR"):
            # Call original function
            result = original_log_error_with_traceback(message, error, level)
            
            # Get stack trace
            stack_trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            
            # Send to webhook
            log_error_to_webhook(error, message=message, level=level, stack_trace=stack_trace)
            
            return result
        
        # Patch log_run_header
        def patched_log_run_header(name, version):
            # Call original function
            result = original_log_run_header(name, version)
            
            # Send to webhook
            log_to_webhook(LogLevel.INFO, f"Bot Started: {name} v{version}", 
                         bot_name=name, version=version)
            
            return result
        
        # Patch log_run_end
        def patched_log_run_end(message):
            # Call original function
            result = original_log_run_end(message)
            
            # Send to webhook
            log_to_webhook(LogLevel.INFO, f"Bot Stopped: {message}", 
                         message=message)
            
            return result
        
        # Apply patches
        import src.utils.tree_log
        src.utils.tree_log.log_perfect_tree_section = patched_log_perfect_tree_section
        src.utils.tree_log.log_error_with_traceback = patched_log_error_with_traceback
        src.utils.tree_log.log_run_header = patched_log_run_header
        src.utils.tree_log.log_run_end = patched_log_run_end
        
        logger.info("Successfully integrated webhook logging with tree_log")
        return True
    except Exception as e:
        logger.error(f"Failed to integrate webhook logging with tree_log: {str(e)}")
        return False

# Integration with performance.py
def integrate_with_performance_monitor():
    """
    Integrate webhook logging with performance monitoring.
    
    This function patches the performance monitoring functions to also send alerts to webhooks.
    """
    try:
        from src.utils.performance import performance_monitor
        
        # Store original _check_memory_thresholds method
        original_check_memory_thresholds = performance_monitor._check_memory_thresholds
        
        # Patch _check_memory_thresholds
        def patched_check_memory_thresholds(self, memory_usage):
            # Call original method
            original_check_memory_thresholds(memory_usage)
            
            # Send alerts to webhook if thresholds exceeded
            if memory_usage > self.thresholds['memory_critical']:
                log_performance_alert_to_webhook(
                    "memory_usage",
                    memory_usage,
                    self.thresholds['memory_critical'],
                    severity="CRITICAL",
                    message=f"Critical memory usage: {memory_usage:.2f}MB"
                )
            elif memory_usage > self.thresholds['memory_warning']:
                log_performance_alert_to_webhook(
                    "memory_usage",
                    memory_usage,
                    self.thresholds['memory_warning'],
                    severity="WARNING",
                    message=f"High memory usage: {memory_usage:.2f}MB"
                )
        
        # Apply patch
        performance_monitor._check_memory_thresholds = patched_check_memory_thresholds.__get__(
            performance_monitor, type(performance_monitor)
        )
        
        logger.info("Successfully integrated webhook logging with performance monitor")
        return True
    except Exception as e:
        logger.error(f"Failed to integrate webhook logging with performance monitor: {str(e)}")
        return False

# Integration with StatsBot member events
def integrate_with_member_events(bot):
    """
    Integrate webhook logging with member events.
    
    This function patches the bot's member event handlers to also send events to webhooks.
    
    Args:
        bot: The StatsBot instance
    """
    try:
        # Store original event handlers
        original_on_member_join = bot.on_member_join
        original_on_member_remove = bot.on_member_remove
        original_on_member_ban = bot.on_member_ban
        
        # Patch on_member_join
        async def patched_on_member_join(self, member):
            # Call original handler
            await original_on_member_join(member)
            
            # Send to webhook
            log_member_event_to_webhook(
                "join",
                member.id,
                str(member),
                guild_id=member.guild.id,
                guild_name=member.guild.name
            )
        
        # Patch on_member_remove
        async def patched_on_member_remove(self, member):
            # Call original handler
            await original_on_member_remove(member)
            
            # Send to webhook
            log_member_event_to_webhook(
                "leave",
                member.id,
                str(member),
                guild_id=member.guild.id,
                guild_name=member.guild.name
            )
        
        # Patch on_member_ban
        async def patched_on_member_ban(self, guild, user):
            # Call original handler
            await original_on_member_ban(guild, user)
            
            # Send to webhook
            log_member_event_to_webhook(
                "ban",
                user.id,
                str(user),
                guild_id=guild.id,
                guild_name=guild.name
            )
        
        # Apply patches
        bot.on_member_join = patched_on_member_join.__get__(bot, type(bot))
        bot.on_member_remove = patched_on_member_remove.__get__(bot, type(bot))
        bot.on_member_ban = patched_on_member_ban.__get__(bot, type(bot))
        
        logger.info("Successfully integrated webhook logging with member events")
        return True
    except Exception as e:
        logger.error(f"Failed to integrate webhook logging with member events: {str(e)}")
        return False