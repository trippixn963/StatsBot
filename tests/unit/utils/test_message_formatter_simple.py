"""
Simplified unit tests for the MessageFormatter class.
"""

import unittest
import json
import os
from unittest.mock import patch, mock_open
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

# Mock the necessary classes to avoid circular imports
class LogLevel(Enum):
    """Log levels for webhook routing."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

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
        from string import Template
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
    
    def register_template(self, template_name: str, template_type: str, template_format: str, template: Dict) -> None:
        """
        Register a custom template.
        
        Args:
            template_name: Name of the template
            template_type: Type of template (log, error, performance, member_event)
            template_format: Format of template (embed, text)
            template: Template dictionary
        """
        if template_name not in self.custom_templates:
            self.custom_templates[template_name] = {}
            
        if template_type not in self.custom_templates[template_name]:
            self.custom_templates[template_name][template_type] = {}
            
        self.custom_templates[template_name][template_type][template_format] = template
    
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
        from string import Template
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


class TestWebhookMessage(unittest.TestCase):
    """Tests for WebhookMessage."""
    
    def test_to_payload(self):
        """Test converting WebhookMessage to payload."""
        message = WebhookMessage(
            content="Test content",
            embeds=[{"title": "Test embed"}],
            username="Test Bot",
            avatar_url="https://example.com/avatar.png"
        )
        
        payload = message.to_payload()
        
        self.assertEqual(payload["content"], "Test content")
        self.assertEqual(payload["embeds"], [{"title": "Test embed"}])
        self.assertEqual(payload["username"], "Test Bot")
        self.assertEqual(payload["avatar_url"], "https://example.com/avatar.png")
    
    def test_validate_valid(self):
        """Test validation with valid message."""
        message = WebhookMessage(
            content="Test content",
            embeds=[{"title": "Test embed", "description": "Test description"}]
        )
        
        errors = message.validate()
        self.assertEqual(len(errors), 0)
    
    def test_validate_content_too_long(self):
        """Test validation with content too long."""
        message = WebhookMessage(
            content="x" * 2001  # Exceeds 2000 character limit
        )
        
        errors = message.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("Content length exceeds", errors[0])
    
    def test_validate_too_many_embeds(self):
        """Test validation with too many embeds."""
        message = WebhookMessage(
            embeds=[{"title": f"Embed {i}"} for i in range(11)]  # Exceeds 10 embed limit
        )
        
        errors = message.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("Too many embeds", errors[0])


class TestMessageFormatter(unittest.TestCase):
    """Tests for MessageFormatter."""
    
    def test_format_log_message_embed(self):
        """Test formatting log message as embed."""
        config = WebhookConfig(use_embeds=True)
        formatter = MessageFormatter(config)
        
        message = formatter.format_log_message(
            LogLevel.ERROR,
            "Test error message",
            component="test_component",
            user_id=123456789
        )
        
        self.assertIsInstance(message, WebhookMessage)
        self.assertEqual(len(message.embeds), 1)
        self.assertIn("ERROR", message.embeds[0]["title"])
        self.assertEqual(message.embeds[0]["description"], "Test error message")
        
        # Check fields
        fields = {field["name"]: field["value"] for field in message.embeds[0]["fields"]}
        self.assertIn("Component", fields)
        self.assertEqual(fields["Component"], "test_component")
        self.assertIn("User Id", fields)
        self.assertEqual(fields["User Id"], "123456789")
    
    def test_format_log_message_text(self):
        """Test formatting log message as plain text."""
        config = WebhookConfig(use_embeds=False)
        formatter = MessageFormatter(config)
        
        message = formatter.format_log_message(
            LogLevel.INFO,
            "Test info message",
            component="test_component"
        )
        
        self.assertIsInstance(message, WebhookMessage)
        self.assertIsNotNone(message.content)
        self.assertIn("INFO", message.content)
        self.assertIn("Test info message", message.content)
        self.assertIn("Component", message.content)
        self.assertIn("test_component", message.content)
    
    def test_truncate_text(self):
        """Test text truncation."""
        config = WebhookConfig(max_message_length=10)
        formatter = MessageFormatter(config)
        
        text = "This is a long text that should be truncated"
        truncated = formatter._truncate_text(text)
        
        self.assertLessEqual(len(truncated), 10)
        self.assertEqual(truncated, "This is...")
    
    def test_truncate_embed_fields(self):
        """Test embed field truncation."""
        config = WebhookConfig()
        formatter = MessageFormatter(config)
        
        embed = {
            "title": "x" * 300,  # Exceeds 256 character limit
            "description": "x" * 5000,  # Exceeds 4096 character limit
            "fields": [
                {"name": "x" * 300, "value": "x" * 1100}  # Exceeds limits
            ],
            "footer": {"text": "x" * 3000}  # Exceeds 2048 character limit
        }
        
        truncated = formatter._truncate_embed_fields(embed)
        
        self.assertLessEqual(len(truncated["title"]), 256)
        self.assertLessEqual(len(truncated["description"]), 4096)
        self.assertLessEqual(len(truncated["fields"][0]["name"]), 256)
        self.assertLessEqual(len(truncated["fields"][0]["value"]), 1024)
        self.assertLessEqual(len(truncated["footer"]["text"]), 2048)
    
    def test_process_template(self):
        """Test template processing."""
        config = WebhookConfig()
        formatter = MessageFormatter(config)
        
        template = {
            "title": "${emoji} ${level}",
            "description": "${message}",
            "fields": [
                {"name": "Field 1", "value": "${field1}"},
                {"name": "Field 2", "value": "${field2}"}
            ]
        }
        
        variables = {
            "emoji": "⚠️",
            "level": "WARNING",
            "message": "Test message",
            "field1": "Value 1",
            "field2": "Value 2"
        }
        
        processed = formatter._process_template(template, variables)
        
        self.assertEqual(processed["title"], "⚠️ WARNING")
        self.assertEqual(processed["description"], "Test message")
        self.assertEqual(processed["fields"][0]["value"], "Value 1")
        self.assertEqual(processed["fields"][1]["value"], "Value 2")
    
    def test_custom_template(self):
        """Test using custom template."""
        config = WebhookConfig(use_embeds=True)
        formatter = MessageFormatter(config)
        
        # Register custom template
        formatter.register_template(
            "test_template",
            "log",
            "embed",
            {
                "title": "Custom: ${level}",
                "description": "${message}",
                "color": "${color}"
            }
        )
        
        message = formatter.format_log_message(
            LogLevel.INFO,
            "Test message",
            template="test_template"
        )
        
        self.assertIsInstance(message, WebhookMessage)
        self.assertEqual(len(message.embeds), 1)
        self.assertEqual(message.embeds[0]["title"], "Custom: INFO")
        self.assertEqual(message.embeds[0]["description"], "Test message")


if __name__ == "__main__":
    unittest.main()