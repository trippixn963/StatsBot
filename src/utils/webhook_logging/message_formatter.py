"""
Message formatting for Discord webhooks.

This module handles formatting log messages, errors, performance alerts,
and other events into Discord webhook messages with proper formatting.
It supports customizable templates, variable substitution, and rich embed formatting.
"""

import traceback
import re
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Callable
from string import Template

from .config import WebhookConfig, LogLevel

@dataclass
class WebhookMessage:
    """Represents a formatted webhook message."""
    
    content: Optional[str] = None
    embeds: List[Dict[str, Any]] = field(default_factory=list)
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    
    def to_payload(self) -> Dict[str, Any]:
        """
        Convert to Discord webhook payload.
        
        Returns:
            Dict: Discord webhook API payload
        """
        payload = {}
        
        if self.content:
            payload["content"] = self.content
        
        if self.embeds:
            payload["embeds"] = self.embeds
        
        if self.username:
            payload["username"] = self.username
        
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url
        
        return payload
        
    def validate(self) -> List[str]:
        """
        Validate the webhook message against Discord's limits.
        
        Returns:
            List[str]: List of validation errors, empty if valid.
        """
        errors = []
        
        # Check content length
        if self.content and len(self.content) > 2000:
            errors.append(f"Content length exceeds Discord's limit of 2000 characters: {len(self.content)}")
        
        # Check embeds
        if self.embeds:
            if len(self.embeds) > 10:
                errors.append(f"Too many embeds: {len(self.embeds)}. Discord allows a maximum of 10.")
            
            for i, embed in enumerate(self.embeds):
                # Check title
                if "title" in embed and len(embed["title"]) > 256:
                    errors.append(f"Embed {i} title exceeds Discord's limit of 256 characters: {len(embed['title'])}")
                
                # Check description
                if "description" in embed and len(embed["description"]) > 4096:
                    errors.append(f"Embed {i} description exceeds Discord's limit of 4096 characters: {len(embed['description'])}")
                
                # Check fields
                if "fields" in embed:
                    if len(embed["fields"]) > 25:
                        errors.append(f"Embed {i} has too many fields: {len(embed['fields'])}. Discord allows a maximum of 25.")
                    
                    for j, field in enumerate(embed["fields"]):
                        if "name" in field and len(field["name"]) > 256:
                            errors.append(f"Embed {i} field {j} name exceeds Discord's limit of 256 characters: {len(field['name'])}")
                        if "value" in field and len(field["value"]) > 1024:
                            errors.append(f"Embed {i} field {j} value exceeds Discord's limit of 1024 characters: {len(field['value'])}")
                
                # Check footer
                if "footer" in embed and "text" in embed["footer"] and len(embed["footer"]["text"]) > 2048:
                    errors.append(f"Embed {i} footer text exceeds Discord's limit of 2048 characters: {len(embed['footer']['text'])}")
                
                # Check author
                if "author" in embed and "name" in embed["author"] and len(embed["author"]["name"]) > 256:
                    errors.append(f"Embed {i} author name exceeds Discord's limit of 256 characters: {len(embed['author']['name'])}")
        
        return errors


class MessageFormatter:
    """
    Formats log messages for Discord webhook delivery.
    
    Supports both plain text and rich embed formatting with
    customizable templates and variable substitution.
    """
    
    # Default templates for different message types
    DEFAULT_TEMPLATES = {
        "log": {
            "embed": {
                "title": "${emoji} ${level}",
                "description": "${message}",
                "color": "${color}",
                "timestamp": "${timestamp}",
                "footer": {
                    "text": "StatsBot Logger"
                }
            },
            "text": "**[${timestamp}] ${emoji} ${level}**: ${message}\n\n${context}"
        },
        "error": {
            "embed": {
                "title": "${emoji} Error: ${error_type}",
                "description": "${message}",
                "color": "${color}",
                "fields": [
                    {"name": "Error Type", "value": "${error_type}", "inline": True},
                    {"name": "Component", "value": "${component}", "inline": True},
                    {"name": "Timestamp", "value": "${timestamp}", "inline": True}
                ],
                "footer": {
                    "text": "StatsBot Error Monitor"
                }
            },
            "text": "**[${timestamp}] ${emoji} ERROR**: ${message}\n**Type**: ${error_type}\n\n${context}\n\n**Stack Trace**:\n```\n${stack_trace}\n```"
        },
        "performance": {
            "embed": {
                "title": "${emoji} Performance Alert: ${metric_name}",
                "description": "Performance metric **${metric_name}** has exceeded threshold.",
                "color": "${color}",
                "fields": [
                    {"name": "Current Value", "value": "${value}", "inline": True},
                    {"name": "Threshold", "value": "${threshold}", "inline": True},
                    {"name": "Ratio", "value": "${ratio}x", "inline": True}
                ],
                "timestamp": "${timestamp}",
                "footer": {
                    "text": "StatsBot Performance Monitor"
                }
            },
            "text": "**${emoji} Performance Alert: ${metric_name}**\nPerformance metric **${metric_name}** has exceeded threshold.\n\n- **Current Value**: ${value}\n- **Threshold**: ${threshold}\n- **Ratio**: ${ratio}x\n\n${context}"
        },
        "member_event": {
            "embed": {
                "title": "${emoji} ${title}",
                "description": "**${username}** (${member_id})",
                "color": "${color}",
                "timestamp": "${timestamp}",
                "footer": {
                    "text": "StatsBot Member Events"
                }
            },
            "text": "**${emoji} ${title}**\n**${username}** (${member_id})\n\n${context}"
        }
    }
    
    def __init__(self, config: WebhookConfig):
        """
        Initialize message formatter.
        
        Args:
            config: Webhook configuration
        """
        self.config = config
        
        # Default colors for different log levels
        self.level_colors = {
            LogLevel.DEBUG: 0x7289DA,     # Blurple
            LogLevel.INFO: 0x3498DB,      # Blue
            LogLevel.WARNING: 0xF1C40F,   # Yellow
            LogLevel.ERROR: 0xE74C3C,     # Red
            LogLevel.CRITICAL: 0x992D22,  # Dark Red
        }
        
        # Default emojis for different log levels
        self.level_emojis = {
            LogLevel.DEBUG: "🔍",
            LogLevel.INFO: "ℹ️",
            LogLevel.WARNING: "⚠️",
            LogLevel.ERROR: "❌",
            LogLevel.CRITICAL: "🚨",
        }
        
        # Load custom templates if provided
        self.templates = self.DEFAULT_TEMPLATES.copy()
        self.custom_templates = {}
    
    def _process_template(self, template_dict: Dict, variables: Dict) -> Dict:
        """
        Process a template dictionary by substituting variables.
        
        Args:
            template_dict: Template dictionary
            variables: Variables to substitute
            
        Returns:
            Dict: Processed template with variables substituted
        """
        result = {}
        
        for key, value in template_dict.items():
            if isinstance(value, dict):
                # Recursively process nested dictionaries
                result[key] = self._process_template(value, variables)
            elif isinstance(value, list):
                # Process lists of dictionaries or strings
                result[key] = [
                    self._process_template(item, variables) if isinstance(item, dict)
                    else Template(item).safe_substitute(variables) if isinstance(item, str)
                    else item
                    for item in value
                ]
            elif isinstance(value, str):
                # Substitute variables in string
                result[key] = Template(value).safe_substitute(variables)
            else:
                # Keep other values as is
                result[key] = value
                
        return result
    
    def _format_context_as_fields(self, context: Dict) -> List[Dict[str, Any]]:
        """
        Format context dictionary as embed fields.
        
        Args:
            context: Context dictionary
            
        Returns:
            List[Dict]: List of embed fields
        """
        fields = []
        
        for key, value in context.items():
            if key not in ["stack_trace", "message", "level", "timestamp", "color", "emoji"]:
                fields.append({
                    "name": key.replace("_", " ").title(),
                    "value": str(value),
                    "inline": True
                })
        
        return fields
    
    def _format_context_as_text(self, context: Dict) -> str:
        """
        Format context dictionary as text.
        
        Args:
            context: Context dictionary
            
        Returns:
            str: Formatted context text
        """
        if not context:
            return ""
            
        text = "**Context:**\n"
        for key, value in context.items():
            if key not in ["stack_trace", "message", "level", "timestamp", "color", "emoji"]:
                text += f"- **{key.replace('_', ' ').title()}**: {value}\n"
        
        return text
    
    def _truncate_text(self, text: str, max_length: int = None) -> str:
        """
        Truncate text to maximum length.
        
        Args:
            text: Text to truncate
            max_length: Maximum length (defaults to config.max_message_length)
            
        Returns:
            str: Truncated text
        """
        if max_length is None:
            max_length = self.config.max_message_length
            
        if len(text) <= max_length:
            return text
            
        # Truncate and add indicator
        return text[:max_length - 3] + "..."
    
    def _truncate_embed_fields(self, embed: Dict) -> Dict:
        """
        Truncate embed fields to comply with Discord limits.
        
        Args:
            embed: Discord embed dictionary
            
        Returns:
            Dict: Truncated embed
        """
        # Discord embed limits
        EMBED_TITLE_LIMIT = 256
        EMBED_DESCRIPTION_LIMIT = 4096
        EMBED_FIELD_NAME_LIMIT = 256
        EMBED_FIELD_VALUE_LIMIT = 1024
        EMBED_FOOTER_TEXT_LIMIT = 2048
        EMBED_AUTHOR_NAME_LIMIT = 256
        
        result = embed.copy()
        
        # Truncate title
        if "title" in result and isinstance(result["title"], str):
            result["title"] = self._truncate_text(result["title"], EMBED_TITLE_LIMIT)
            
        # Truncate description
        if "description" in result and isinstance(result["description"], str):
            result["description"] = self._truncate_text(result["description"], EMBED_DESCRIPTION_LIMIT)
            
        # Truncate fields
        if "fields" in result and isinstance(result["fields"], list):
            for field in result["fields"]:
                if "name" in field and isinstance(field["name"], str):
                    field["name"] = self._truncate_text(field["name"], EMBED_FIELD_NAME_LIMIT)
                if "value" in field and isinstance(field["value"], str):
                    field["value"] = self._truncate_text(field["value"], EMBED_FIELD_VALUE_LIMIT)
                    
        # Truncate footer
        if "footer" in result and isinstance(result["footer"], dict):
            if "text" in result["footer"] and isinstance(result["footer"]["text"], str):
                result["footer"]["text"] = self._truncate_text(result["footer"]["text"], EMBED_FOOTER_TEXT_LIMIT)
                
        # Truncate author
        if "author" in result and isinstance(result["author"], dict):
            if "name" in result["author"] and isinstance(result["author"]["name"], str):
                result["author"]["name"] = self._truncate_text(result["author"]["name"], EMBED_AUTHOR_NAME_LIMIT)
                
        return result
    
    def register_template(self, template_type: str, template_name: str, template: Dict) -> None:
        """
        Register a custom template.
        
        Args:
            template_type: Type of template (log, error, performance, member_event)
            template_name: Name of the template
            template: Template dictionary
        """
        if template_type not in self.templates:
            self.templates[template_type] = {}
            
        if template_name not in self.custom_templates:
            self.custom_templates[template_name] = {}
            
        self.custom_templates[template_name][template_type] = template
    
    def format_log_message(self, level: LogLevel, message: str, **context) -> WebhookMessage:
        """
        Format standard log message.
        
        Args:
            level: Log level
            message: Log message
            **context: Additional context for the message
            
        Returns:
            WebhookMessage: Formatted webhook message
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Prepare variables for template substitution
        variables = {
            "level": level.value.upper(),
            "message": message,
            "timestamp": timestamp,
            "emoji": self.level_emojis.get(level, ""),
            "color": hex(self.level_colors.get(level, 0x000000)),
            **context
        }
        
        # Get template based on message type and format
        template_type = "log"
        template_format = "embed" if self.config.use_embeds else "text"
        
        # Get custom template if specified
        template_name = context.get("template", "default")
        if template_name != "default" and template_name in self.custom_templates:
            if template_type in self.custom_templates[template_name]:
                if template_format in self.custom_templates[template_name][template_type]:
                    template = self.custom_templates[template_name][template_type][template_format]
                else:
                    # Fall back to default format
                    template = self.templates[template_type][template_format]
            else:
                # Fall back to default template
                template = self.templates[template_type][template_format]
        else:
            # Use default template
            template = self.templates[template_type][template_format]
        
        if self.config.use_embeds:
            # Process embed template
            embed = self._process_template(template, variables)
            
            # Add context fields if not already in template
            if "fields" not in embed or not embed["fields"]:
                embed["fields"] = self._format_context_as_fields(context)
            
            # Add stack trace if available and not already in template
            if "stack_trace" in context and self.config.include_stack_traces:
                stack_trace = context["stack_trace"]
                truncated_stack_trace = self._truncate_text(stack_trace, 1000)
                
                # Check if stack trace field already exists
                stack_trace_field_exists = False
                if "fields" in embed:
                    for field in embed["fields"]:
                        if field.get("name") == "Stack Trace":
                            stack_trace_field_exists = True
                            break
                
                if not stack_trace_field_exists:
                    if "fields" not in embed:
                        embed["fields"] = []
                    embed["fields"].append({
                        "name": "Stack Trace",
                        "value": f"```\n{truncated_stack_trace}\n```",
                        "inline": False
                    })
            
            # Truncate embed fields to comply with Discord limits
            embed = self._truncate_embed_fields(embed)
            
            return WebhookMessage(
                embeds=[embed],
                username="StatsBot Logger"
            )
        else:
            # Process text template
            content = Template(template).safe_substitute(variables)
            
            # Replace ${context} placeholder with formatted context
            if "${context}" in content:
                content = content.replace("${context}", self._format_context_as_text(context))
            
            # Add stack trace if available and not already in template
            if "stack_trace" in context and self.config.include_stack_traces and "stack_trace" not in content:
                stack_trace = context["stack_trace"]
                truncated_stack_trace = self._truncate_text(stack_trace, 1000)
                content += f"\n\n**Stack Trace:**\n```\n{truncated_stack_trace}\n```"
            
            # Truncate content to maximum message length
            content = self._truncate_text(content)
            
            return WebhookMessage(
                content=content,
                username="StatsBot Logger"
            )
    
    def format_error_message(self, error: Exception, context: Dict) -> WebhookMessage:
        """
        Format error messages with stack traces.
        
        Args:
            error: Exception object
            context: Additional context for the error
            
        Returns:
            WebhookMessage: Formatted webhook message
        """
        # Get error details
        error_type = type(error).__name__
        error_message = str(error)
        stack_trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        
        # Add error info to context
        context.update({
            "error_type": error_type,
            "stack_trace": stack_trace,
            "message": error_message
        })
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Prepare variables for template substitution
        variables = {
            "level": "ERROR",
            "message": error_message,
            "timestamp": timestamp,
            "emoji": self.level_emojis.get(LogLevel.ERROR, "❌"),
            "color": hex(self.level_colors.get(LogLevel.ERROR, 0xE74C3C)),
            "error_type": error_type,
            "stack_trace": stack_trace,
            **context
        }
        
        # Get template based on message type and format
        template_type = "error"
        template_format = "embed" if self.config.use_embeds else "text"
        
        # Get custom template if specified
        template_name = context.get("template", "default")
        if template_name != "default" and template_name in self.custom_templates:
            if template_type in self.custom_templates[template_name]:
                if template_format in self.custom_templates[template_name][template_type]:
                    template = self.custom_templates[template_name][template_type][template_format]
                else:
                    # Fall back to default format
                    template = self.templates[template_type][template_format]
            else:
                # Fall back to default template
                template = self.templates[template_type][template_format]
        else:
            # Use default template
            template = self.templates[template_type][template_format]
        
        if self.config.use_embeds:
            # Process embed template
            embed = self._process_template(template, variables)
            
            # Add context fields if not already in template
            if "fields" not in embed or not embed["fields"]:
                embed["fields"] = self._format_context_as_fields(context)
            
            # Add stack trace if available and not already in template
            if self.config.include_stack_traces:
                # Check if stack trace field already exists
                stack_trace_field_exists = False
                if "fields" in embed:
                    for field in embed["fields"]:
                        if field.get("name") == "Stack Trace":
                            stack_trace_field_exists = True
                            break
                
                if not stack_trace_field_exists:
                    if "fields" not in embed:
                        embed["fields"] = []
                    embed["fields"].append({
                        "name": "Stack Trace",
                        "value": f"```\n{self._truncate_text(stack_trace, 1000)}\n```",
                        "inline": False
                    })
            
            # Truncate embed fields to comply with Discord limits
            embed = self._truncate_embed_fields(embed)
            
            return WebhookMessage(
                embeds=[embed],
                username="StatsBot Error Logger"
            )
        else:
            # Process text template
            content = Template(template).safe_substitute(variables)
            
            # Replace ${context} placeholder with formatted context
            if "${context}" in content:
                content = content.replace("${context}", self._format_context_as_text(context))
            
            # Truncate content to maximum message length
            content = self._truncate_text(content)
            
            return WebhookMessage(
                content=content,
                username="StatsBot Error Logger"
            )
    
    def format_performance_alert(self, metric_name: str, value: float, 
                               threshold: float, **context) -> WebhookMessage:
        """
        Format performance monitoring alerts.
        
        Args:
            metric_name: Name of the performance metric
            value: Current metric value
            threshold: Threshold that triggered the alert
            **context: Additional context for the alert
            
        Returns:
            WebhookMessage: Formatted webhook message
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Determine severity based on how far over threshold
        severity_ratio = value / threshold
        
        if severity_ratio >= 2.0:
            level = LogLevel.CRITICAL
            emoji = "🚨"
        elif severity_ratio >= 1.5:
            level = LogLevel.ERROR
            emoji = "❌"
        else:
            level = LogLevel.WARNING
            emoji = "⚠️"
        
        # Format values for display
        formatted_value = f"{value:.2f}"
        formatted_threshold = f"{threshold:.2f}"
        formatted_ratio = f"{severity_ratio:.2f}"
        
        # Prepare variables for template substitution
        variables = {
            "metric_name": metric_name,
            "value": formatted_value,
            "threshold": formatted_threshold,
            "ratio": formatted_ratio,
            "timestamp": timestamp,
            "emoji": emoji,
            "color": hex(self.level_colors.get(level, 0xFFA500)),
            "level": level.value.upper(),
            **context
        }
        
        # Get template based on message type and format
        template_type = "performance"
        template_format = "embed" if self.config.use_embeds else "text"
        
        # Get custom template if specified
        template_name = context.get("template", "default")
        if template_name != "default" and template_name in self.custom_templates:
            if template_type in self.custom_templates[template_name]:
                if template_format in self.custom_templates[template_name][template_type]:
                    template = self.custom_templates[template_name][template_type][template_format]
                else:
                    # Fall back to default format
                    template = self.templates[template_type][template_format]
            else:
                # Fall back to default template
                template = self.templates[template_type][template_format]
        else:
            # Use default template
            template = self.templates[template_type][template_format]
        
        if self.config.use_embeds:
            # Process embed template
            embed = self._process_template(template, variables)
            
            # Add context fields if not already in template
            context_fields = self._format_context_as_fields({k: v for k, v in context.items() 
                                                          if k not in ["metric_name", "value", "threshold", "ratio"]})
            
            if context_fields:
                if "fields" not in embed:
                    embed["fields"] = []
                embed["fields"].extend(context_fields)
            
            # Truncate embed fields to comply with Discord limits
            embed = self._truncate_embed_fields(embed)
            
            return WebhookMessage(
                embeds=[embed],
                username="StatsBot Performance Monitor"
            )
        else:
            # Process text template
            content = Template(template).safe_substitute(variables)
            
            # Replace ${context} placeholder with formatted context
            if "${context}" in content:
                context_text = self._format_context_as_text({k: v for k, v in context.items() 
                                                          if k not in ["metric_name", "value", "threshold", "ratio"]})
                content = content.replace("${context}", context_text)
            
            # Truncate content to maximum message length
            content = self._truncate_text(content)
            
            return WebhookMessage(
                content=content,
                username="StatsBot Performance Monitor"
            )
    
    def format_member_event(self, event_type: str, member_id: int, 
                          username: str, **context) -> WebhookMessage:
        """
        Format member join/leave/ban events.
        
        Args:
            event_type: Type of event (join, leave, ban, etc.)
            member_id: Discord member ID
            username: Discord username
            **context: Additional context for the event
            
        Returns:
            WebhookMessage: Formatted webhook message
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Apply privacy settings
        if self.config.mask_user_ids:
            member_id_str = f"{str(member_id)[:5]}...{str(member_id)[-4:]}"
        else:
            member_id_str = str(member_id)
        
        # Event type specific formatting
        if event_type == "join":
            emoji = "📥"
            title = "Member Joined"
            color = 0x2ECC71  # Green
        elif event_type == "leave":
            emoji = "📤"
            title = "Member Left"
            color = 0xE67E22  # Orange
        elif event_type == "ban":
            emoji = "🔨"
            title = "Member Banned"
            color = 0xE74C3C  # Red
        elif event_type == "unban":
            emoji = "🔓"
            title = "Member Unbanned"
            color = 0x3498DB  # Blue
        else:
            emoji = "👤"
            title = f"Member {event_type.title()}"
            color = 0x7289DA  # Blurple
        
        # Prepare variables for template substitution
        variables = {
            "event_type": event_type,
            "member_id": member_id_str,
            "username": username,
            "timestamp": timestamp,
            "emoji": emoji,
            "title": title,
            "color": hex(color),
            **context
        }
        
        # Get template based on message type and format
        template_type = "member_event"
        template_format = "embed" if self.config.use_embeds else "text"
        
        # Get custom template if specified
        template_name = context.get("template", "default")
        if template_name != "default" and template_name in self.custom_templates:
            if template_type in self.custom_templates[template_name]:
                if template_format in self.custom_templates[template_name][template_type]:
                    template = self.custom_templates[template_name][template_type][template_format]
                else:
                    # Fall back to default format
                    template = self.templates[template_type][template_format]
            else:
                # Fall back to default template
                template = self.templates[template_type][template_format]
        else:
            # Use default template
            template = self.templates[template_type][template_format]
        
        if self.config.use_embeds:
            # Process embed template
            embed = self._process_template(template, variables)
            
            # Add context fields if not already in template
            context_fields = self._format_context_as_fields({k: v for k, v in context.items() 
                                                          if k not in ["event_type", "member_id", "username"]})
            
            if context_fields:
                if "fields" not in embed:
                    embed["fields"] = []
                embed["fields"].extend(context_fields)
            
            # Truncate embed fields to comply with Discord limits
            embed = self._truncate_embed_fields(embed)
            
            return WebhookMessage(
                embeds=[embed],
                username="StatsBot Member Events"
            )
        else:
            # Process text template
            content = Template(template).safe_substitute(variables)
            
            # Replace ${context} placeholder with formatted context
            if "${context}" in content:
                context_text = self._format_context_as_text({k: v for k, v in context.items() 
                                                          if k not in ["event_type", "member_id", "username"]})
                content = content.replace("${context}", context_text)
            
            # Truncate content to maximum message length
            content = self._truncate_text(content)
            
            return WebhookMessage(
                content=content,
                username="StatsBot Member Events"
            )

def load_template_from_file(file_path: str) -> Dict:
    """
    Load a template from a JSON file.
    
    Args:
        file_path: Path to the template file
        
    Returns:
        Dict: Loaded template
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file isn't valid JSON
    """
    with open(file_path, 'r') as f:
        return json.load(f)

class TemplateManager:
    """
    Manages templates for webhook messages.
    
    This class handles loading, validating, and storing templates
    for different types of webhook messages.
    """
    
    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialize template manager.
        
        Args:
            template_dir: Optional directory to load templates from
        """
        self.templates = {}
        self.template_dir = template_dir
        
        # Load default templates
        self.templates["default"] = MessageFormatter.DEFAULT_TEMPLATES
        
        # Load templates from directory if provided
        if template_dir:
            self.load_templates_from_directory(template_dir)
    
    def load_templates_from_directory(self, directory: str) -> None:
        """
        Load templates from a directory.
        
        Args:
            directory: Directory containing template files
        """
        import os
        
        if not os.path.exists(directory):
            return
        
        for filename in os.listdir(directory):
            if filename.endswith(".json"):
                try:
                    template_name = os.path.splitext(filename)[0]
                    template_path = os.path.join(directory, filename)
                    self.templates[template_name] = load_template_from_file(template_path)
                except Exception as e:
                    import logging
                    logger = logging.getLogger("webhook_logging")
                    logger.warning(f"Failed to load template {filename}: {str(e)}")
    
    def get_template(self, template_name: str, template_type: str, template_format: str) -> Optional[Dict]:
        """
        Get a template.
        
        Args:
            template_name: Name of the template
            template_type: Type of template (log, error, performance, member_event)
            template_format: Format of template (embed, text)
            
        Returns:
            Dict: Template dictionary or None if not found
        """
        if template_name in self.templates:
            if template_type in self.templates[template_name]:
                if template_format in self.templates[template_name][template_type]:
                    return self.templates[template_name][template_type][template_format]
        
        # Fall back to default template
        if template_type in self.templates["default"]:
            if template_format in self.templates["default"][template_type]:
                return self.templates["default"][template_type][template_format]
        
        return None
    
    def register_template(self, template_name: str, template_type: str, template_format: str, template: Dict) -> None:
        """
        Register a template.
        
        Args:
            template_name: Name of the template
            template_type: Type of template (log, error, performance, member_event)
            template_format: Format of template (embed, text)
            template: Template dictionary
        """
        if template_name not in self.templates:
            self.templates[template_name] = {}
        
        if template_type not in self.templates[template_name]:
            self.templates[template_name][template_type] = {}
        
        self.templates[template_name][template_type][template_format] = template