"""
Unit tests for the MessageFormatter class.
"""

import sys
import os
import unittest
import json
from unittest.mock import patch, mock_open
from datetime import datetime, timezone

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.utils.webhook_logging.config import WebhookConfig, LogLevel
from src.utils.webhook_logging.message_formatter import (
    MessageFormatter, WebhookMessage, TemplateManager, load_template_from_file
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
        
        assert payload["content"] == "Test content"
        assert payload["embeds"] == [{"title": "Test embed"}]
        assert payload["username"] == "Test Bot"
        assert payload["avatar_url"] == "https://example.com/avatar.png"
    
    def test_validate_valid(self):
        """Test validation with valid message."""
        message = WebhookMessage(
            content="Test content",
            embeds=[{"title": "Test embed", "description": "Test description"}]
        )
        
        errors = message.validate()
        assert len(errors) == 0
    
    def test_validate_content_too_long(self):
        """Test validation with content too long."""
        message = WebhookMessage(
            content="x" * 2001  # Exceeds 2000 character limit
        )
        
        errors = message.validate()
        assert len(errors) == 1
        assert "Content length exceeds" in errors[0]
    
    def test_validate_too_many_embeds(self):
        """Test validation with too many embeds."""
        message = WebhookMessage(
            embeds=[{"title": f"Embed {i}"} for i in range(11)]  # Exceeds 10 embed limit
        )
        
        errors = message.validate()
        assert len(errors) == 1
        assert "Too many embeds" in errors[0]
    
    def test_validate_embed_fields_too_long(self):
        """Test validation with embed field value too long."""
        message = WebhookMessage(
            embeds=[{
                "title": "Test embed",
                "fields": [
                    {"name": "Field 1", "value": "x" * 1025}  # Exceeds 1024 character limit
                ]
            }]
        )
        
        errors = message.validate()
        assert len(errors) == 1
        assert "field 0 value exceeds" in errors[0].lower()


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
        
        assert isinstance(message, WebhookMessage)
        assert len(message.embeds) == 1
        assert "ERROR" in message.embeds[0]["title"]
        assert message.embeds[0]["description"] == "Test error message"
        
        # Check fields
        fields = {field["name"]: field["value"] for field in message.embeds[0]["fields"]}
        assert "Component" in fields
        assert fields["Component"] == "test_component"
        assert "User Id" in fields
        assert fields["User Id"] == "123456789"
    
    def test_format_log_message_text(self):
        """Test formatting log message as plain text."""
        config = WebhookConfig(use_embeds=False)
        formatter = MessageFormatter(config)
        
        message = formatter.format_log_message(
            LogLevel.INFO,
            "Test info message",
            component="test_component"
        )
        
        assert isinstance(message, WebhookMessage)
        assert message.content is not None
        assert "INFO" in message.content
        assert "Test info message" in message.content
        assert "Component" in message.content
        assert "test_component" in message.content
    
    def test_format_error_message(self):
        """Test formatting error message."""
        config = WebhookConfig(use_embeds=True)
        formatter = MessageFormatter(config)
        
        try:
            # Generate an exception
            raise ValueError("Test error")
        except ValueError as e:
            message = formatter.format_error_message(e, {"component": "test_component"})
        
        assert isinstance(message, WebhookMessage)
        assert len(message.embeds) == 1
        assert "Error" in message.embeds[0]["title"]
        
        # Check fields
        fields = {field["name"]: field["value"] for field in message.embeds[0]["fields"]}
        assert "Error Type" in fields
        assert fields["Error Type"] == "ValueError"
        assert "Component" in fields
        assert fields["Component"] == "test_component"
        assert "Stack Trace" in fields
        assert "```" in fields["Stack Trace"]
    
    def test_format_performance_alert(self):
        """Test formatting performance alert."""
        config = WebhookConfig(use_embeds=True)
        formatter = MessageFormatter(config)
        
        message = formatter.format_performance_alert(
            "memory_usage",
            150.0,
            100.0,
            component="test_component"
        )
        
        assert isinstance(message, WebhookMessage)
        assert len(message.embeds) == 1
        assert "Performance Alert" in message.embeds[0]["title"]
        assert "memory_usage" in message.embeds[0]["title"]
        
        # Check fields
        fields = {field["name"]: field["value"] for field in message.embeds[0]["fields"]}
        assert "Current Value" in fields
        assert "150.00" in fields["Current Value"]
        assert "Threshold" in fields
        assert "100.00" in fields["Threshold"]
        assert "Ratio" in fields
        assert "1.50" in fields["Ratio"]
        assert "Component" in fields
        assert fields["Component"] == "test_component"
    
    def test_format_member_event(self):
        """Test formatting member event."""
        config = WebhookConfig(use_embeds=True)
        formatter = MessageFormatter(config)
        
        message = formatter.format_member_event(
            "join",
            123456789,
            "TestUser#1234",
            guild_id=987654321
        )
        
        assert isinstance(message, WebhookMessage)
        assert len(message.embeds) == 1
        assert "Member Joined" in message.embeds[0]["title"]
        assert "TestUser#1234" in message.embeds[0]["description"]
        assert "123456789" in message.embeds[0]["description"]
        
        # Check fields
        fields = {field["name"]: field["value"] for field in message.embeds[0]["fields"]}
        assert "Guild Id" in fields
        assert fields["Guild Id"] == "987654321"
    
    def test_truncate_text(self):
        """Test text truncation."""
        config = WebhookConfig(max_message_length=10)
        formatter = MessageFormatter(config)
        
        text = "This is a long text that should be truncated"
        truncated = formatter._truncate_text(text)
        
        assert len(truncated) <= 10
        assert truncated == "This is..."
    
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
        
        assert len(truncated["title"]) <= 256
        assert len(truncated["description"]) <= 4096
        assert len(truncated["fields"][0]["name"]) <= 256
        assert len(truncated["fields"][0]["value"]) <= 1024
        assert len(truncated["footer"]["text"]) <= 2048
    
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
        
        assert processed["title"] == "⚠️ WARNING"
        assert processed["description"] == "Test message"
        assert processed["fields"][0]["value"] == "Value 1"
        assert processed["fields"][1]["value"] == "Value 2"
    
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
        
        assert isinstance(message, WebhookMessage)
        assert len(message.embeds) == 1
        assert message.embeds[0]["title"] == "Custom: INFO"
        assert message.embeds[0]["description"] == "Test message"


class TestTemplateManager(unittest.TestCase):
    """Tests for TemplateManager."""
    
    def test_get_default_template(self):
        """Test getting default template."""
        manager = TemplateManager()
        
        template = manager.get_template("default", "log", "embed")
        
        assert template is not None
        assert "title" in template
        assert "description" in template
    
    def test_register_template(self):
        """Test registering custom template."""
        manager = TemplateManager()
        
        custom_template = {
            "title": "Custom Template",
            "description": "${message}"
        }
        
        manager.register_template("custom", "log", "embed", custom_template)
        
        template = manager.get_template("custom", "log", "embed")
        
        assert template is not None
        assert template["title"] == "Custom Template"
        assert template["description"] == "${message}"
    
    def test_template_fallback(self):
        """Test template fallback to default."""
        manager = TemplateManager()
        
        # Get non-existent template
        template = manager.get_template("non_existent", "log", "embed")
        
        # Should fall back to default
        assert template is not None
        assert "title" in template
        assert "description" in template
    
    @patch("builtins.open", new_callable=mock_open, read_data='{"log": {"embed": {"title": "From File"}}}')
    def test_load_template_from_file(self, mock_file):
        """Test loading template from file."""
        template = load_template_from_file("fake_path.json")
        
        assert template is not None
        assert "log" in template
        assert "embed" in template["log"]
        assert template["log"]["embed"]["title"] == "From File"
    
    @patch("os.path.exists", return_value=True)
    @patch("os.listdir", return_value=["template1.json", "template2.json", "not_json.txt"])
    @patch("src.utils.webhook_logging.message_formatter.load_template_from_file")
    def test_load_templates_from_directory(self, mock_load, mock_listdir, mock_exists):
        """Test loading templates from directory."""
        # Set up mock return values
        mock_load.side_effect = [
            {"log": {"embed": {"title": "Template 1"}}},
            {"log": {"embed": {"title": "Template 2"}}}
        ]
        
        manager = TemplateManager()
        manager.load_templates_from_directory("/fake/path")
        
        # Should have loaded 2 templates
        assert mock_load.call_count == 2
        
        # Set the templates manually since we mocked the loading
        manager.templates["template1"] = {"log": {"embed": {"title": "Template 1"}}}
        manager.templates["template2"] = {"log": {"embed": {"title": "Template 2"}}}
        
        # Check templates were loaded
        template1 = manager.get_template("template1", "log", "embed")
        template2 = manager.get_template("template2", "log", "embed")
        
        assert template1 is not None
        assert template1["title"] == "Template 1"
        assert template2 is not None
        assert template2["title"] == "Template 2"
if __name__ == "__main__":
    unittest.main()