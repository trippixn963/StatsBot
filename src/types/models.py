"""
Comprehensive data models and type definitions for StatsBot.

This module defines all the data structures used throughout the application
with proper type hints for better type safety and code clarity.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Union, TypedDict, Protocol, Callable, Tuple, Set, Generic, TypeVar
import discord
import json
from pathlib import Path


# Enums for better type safety
class EventType(Enum):
    """Types of member events that can be tracked."""
    JOIN = "join"
    LEAVE = "leave"
    BAN = "ban"
    UNBAN = "unban"


class LogLevel(Enum):
    """Logging levels for structured logging."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ServiceStatus(Enum):
    """Status of various bot services."""
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class CircuitBreakerState(Enum):
    """States of the circuit breaker pattern."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ConnectionState(Enum):
    """States of the connection to Discord."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


# Configuration data models
@dataclass
class BotConfig:
    """
    Type-safe configuration for the bot.
    
    This dataclass ensures all configuration values are properly typed
    and provides defaults where appropriate. It includes comprehensive
    validation to catch configuration errors early.
    """
    # Required Discord configuration
    bot_token: str
    member_count_channel_id: int
    online_count_channel_id: int
    ban_count_channel_id: int
    heartbeat_channel_id: int
    stats_channel_id: int
    guild_id: Optional[int] = None  # Optional but recommended
    
    # Optional configuration with defaults
    update_interval: int = 300  # 5 minutes
    max_backoff: int = 3600  # 1 hour
    log_level: str = "INFO"
    cache_ttl: int = 300  # 5 minutes
    max_retry_attempts: int = 3
    heartbeat_interval: int = 3600  # 1 hour
    presence_update_interval: int = 300  # 5 minutes
    
    # Resource limits
    max_log_entries: int = 1000
    max_cache_size: int = 10000
    memory_warning_threshold: float = 80.0  # Percentage
    memory_critical_threshold: float = 95.0  # Percentage
    
    # Environment-specific settings
    environment: str = "development"  # development, testing, production
    debug_mode: bool = False
    
    def validate(self) -> None:
        """
        Validate configuration values with comprehensive checks.
        
        Raises:
            ValueError: If any configuration value is invalid
        """
        # Required fields validation
        if not self.bot_token:
            raise ValueError("bot_token cannot be empty")
        
        if not isinstance(self.bot_token, str):
            raise ValueError(f"bot_token must be a string, got {type(self.bot_token).__name__}")
            
        # Channel ID validations
        for field_name in ['member_count_channel_id', 'online_count_channel_id', 
                          'ban_count_channel_id', 'heartbeat_channel_id', 'stats_channel_id']:
            value = getattr(self, field_name)
            if not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer, got {type(value).__name__}")
            if value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        
        # Optional guild_id validation
        if self.guild_id is not None and (not isinstance(self.guild_id, int) or self.guild_id <= 0):
            raise ValueError(f"guild_id must be a positive integer if provided")
        
        # Interval validations
        if self.update_interval < 60:
            raise ValueError("update_interval must be at least 60 seconds")
        
        if self.max_backoff < self.update_interval:
            raise ValueError("max_backoff must be greater than update_interval")
            
        if self.heartbeat_interval < 60:
            raise ValueError("heartbeat_interval must be at least 60 seconds")
            
        if self.presence_update_interval < 60:
            raise ValueError("presence_update_interval must be at least 60 seconds")
        
        # Resource limit validations
        if self.max_log_entries <= 0:
            raise ValueError("max_log_entries must be positive")
            
        if self.max_cache_size <= 0:
            raise ValueError("max_cache_size must be positive")
        
        if not (0 < self.memory_warning_threshold < 100):
            raise ValueError("memory_warning_threshold must be between 0 and 100")
        
        if not (0 < self.memory_critical_threshold <= 100):
            raise ValueError("memory_critical_threshold must be between 0 and 100")
        
        if self.memory_warning_threshold >= self.memory_critical_threshold:
            raise ValueError("memory_warning_threshold must be less than memory_critical_threshold")
            
        # Log level validation
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level not in valid_log_levels:
            raise ValueError(f"log_level must be one of {valid_log_levels}")
            
        # Environment validation
        valid_environments = ["development", "testing", "production"]
        if self.environment not in valid_environments:
            raise ValueError(f"environment must be one of {valid_environments}")
            
        # Debug mode validation
        if not isinstance(self.debug_mode, bool):
            raise ValueError(f"debug_mode must be a boolean, got {type(self.debug_mode).__name__}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization."""
        return asdict(self)
        
    def get_environment_specific_defaults(self) -> Dict[str, Any]:
        """Get environment-specific default values."""
        defaults = {}
        
        if self.environment == "development":
            defaults.update({
                "debug_mode": True,
                "log_level": "DEBUG",
                "update_interval": 60,  # More frequent updates in development
                "max_retry_attempts": 2
            })
        elif self.environment == "testing":
            defaults.update({
                "debug_mode": True,
                "log_level": "DEBUG",
                "update_interval": 120,
                "max_retry_attempts": 2
            })
        elif self.environment == "production":
            defaults.update({
                "debug_mode": False,
                "log_level": "INFO",
                "update_interval": 300,
                "max_retry_attempts": 3
            })
            
        return defaults


# Member and event data models
@dataclass
class MemberEvent:
    """
    Represents a member-related event (join, leave, ban, etc.).
    
    This provides a structured way to track member activity
    with proper typing and validation.
    """
    member_id: int
    username: str
    timestamp: datetime
    event_type: EventType
    guild_id: Optional[int] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'member_id': self.member_id,
            'username': self.username,
            'timestamp': self.timestamp.isoformat(),
            'event_type': self.event_type.value,
            'guild_id': self.guild_id,
            'additional_data': self.additional_data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemberEvent':
        """Create from dictionary (for deserialization)."""
        return cls(
            member_id=data['member_id'],
            username=data['username'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            event_type=EventType(data['event_type']),
            guild_id=data.get('guild_id'),
            additional_data=data.get('additional_data', {})
        )


# Statistics data models
@dataclass
class ChannelStats:
    """Current channel statistics snapshot."""
    member_count: int
    online_count: int
    ban_count: int
    last_updated: datetime
    guild_id: Optional[int] = None
    
    def has_changed(self, other: 'ChannelStats') -> bool:
        """Check if stats have changed compared to another snapshot."""
        return (
            self.member_count != other.member_count or
            self.online_count != other.online_count or
            self.ban_count != other.ban_count
        )


class DailyStats(TypedDict):
    """
    Daily statistics summary.
    
    Using TypedDict for JSON compatibility while maintaining type safety.
    """
    date: str
    joins: int
    leaves: int
    bans: int
    unbans: int
    net_change: int
    join_list: List[Dict[str, Any]]
    leave_list: List[Dict[str, Any]]
    ban_list: List[Dict[str, Any]]
    unban_list: List[Dict[str, Any]]


class WeeklyStats(TypedDict):
    """Weekly statistics summary."""
    start_date: str
    end_date: str
    total_joins: int
    total_leaves: int
    total_bans: int
    total_unbans: int
    net_change: int
    daily_breakdown: List[DailyStats]
    most_active_day: Optional[Dict[str, Any]]
    join_list: List[Dict[str, Any]]
    leave_list: List[Dict[str, Any]]
    ban_list: List[Dict[str, Any]]
    unban_list: List[Dict[str, Any]]


# System monitoring data models
@dataclass
class SystemMetrics:
    """System performance metrics."""
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    threads: int
    uptime_seconds: int
    timestamp: datetime = field(default_factory=datetime.now)
    
    def is_memory_warning(self, threshold: float = 80.0) -> bool:
        """Check if memory usage exceeds warning threshold."""
        return self.memory_percent >= threshold
    
    def is_memory_critical(self, threshold: float = 95.0) -> bool:
        """Check if memory usage exceeds critical threshold."""
        return self.memory_percent >= threshold


@dataclass
class CacheStats:
    """Cache performance statistics."""
    total_entries: int
    hit_count: int
    miss_count: int
    eviction_count: int
    memory_usage_bytes: int
    hit_rate: float = field(init=False)
    
    def __post_init__(self):
        """Calculate hit rate after initialization."""
        total_requests = self.hit_count + self.miss_count
        self.hit_rate = self.hit_count / total_requests if total_requests > 0 else 0.0


@dataclass
class MemoryStats:
    """Memory usage statistics."""
    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent_used: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def is_low_memory(self) -> bool:
        """Check if available memory is low."""
        return self.percent_used > 90.0


# Logging data models
@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: datetime
    level: LogLevel
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    service: Optional[str] = None
    operation: Optional[str] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON logging."""
        data = {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level.value,
            'message': self.message,
            'context': self.context
        }
        
        if self.service:
            data['service'] = self.service
        if self.operation:
            data['operation'] = self.operation
        if self.duration_ms is not None:
            data['duration_ms'] = self.duration_ms
        if self.error:
            data['error'] = self.error
            
        return data


# Error handling data models
@dataclass
class RetryConfig:
    """Configuration for retry mechanisms."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number."""
        import random
        
        delay = min(self.base_delay * (self.exponential_base ** attempt), self.max_delay)
        
        if self.jitter:
            # Add random jitter (±25% of delay)
            jitter_amount = delay * 0.25
            delay += random.uniform(-jitter_amount, jitter_amount)
        
        return max(0, delay)


# Service data models
@dataclass
class HeartbeatData:
    """Data included in heartbeat messages."""
    timestamp: datetime
    uptime_seconds: int
    system_metrics: SystemMetrics
    daily_stats: DailyStats
    service_status: Dict[str, ServiceStatus]
    recent_events: List[MemberEvent]
    cache_stats: Optional[CacheStats] = None
    
    def to_embed_dict(self) -> Dict[str, Any]:
        """Convert to dictionary suitable for Discord embed."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'uptime': f"{self.uptime_seconds // 3600}h {(self.uptime_seconds % 3600) // 60}m",
            'cpu_percent': f"{self.system_metrics.cpu_percent:.1f}%",
            'memory_percent': f"{self.system_metrics.memory_percent:.1f}%",
            'daily_joins': self.daily_stats['joins'],
            'daily_leaves': self.daily_stats['leaves'],
            'daily_bans': self.daily_stats['bans'],
            'net_change': self.daily_stats['net_change']
        }


# Discord-specific type aliases for better clarity
ChannelId = int
GuildId = int
UserId = int
MessageId = int
RoleId = int
EmojiId = int
WebhookId = int
CategoryId = int

# Union types for flexible parameter handling
MemberIdentifier = Union[int, str, discord.Member, discord.User]
ChannelIdentifier = Union[int, str, discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]
RoleIdentifier = Union[int, str, discord.Role]
MessageIdentifier = Union[int, discord.Message]

# Generic types for collections
T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')

# Protocol definitions for interfaces
class Serializable(Protocol):
    """Protocol for objects that can be serialized to dict."""
    def to_dict(self) -> Dict[str, Any]: ...

class Validatable(Protocol):
    """Protocol for objects that can be validated."""
    def validate(self) -> None: ...

class AsyncInitializable(Protocol):
    """Protocol for objects that can be initialized asynchronously."""
    async def initialize(self) -> None: ...

class AsyncCleanable(Protocol):
    """Protocol for objects that can be cleaned up asynchronously."""
    async def cleanup(self) -> None: ...

# Additional enums for better type safety
class FileOperation(Enum):
    """Types of file operations that can be performed."""
    READ = auto()
    WRITE = auto()
    APPEND = auto()
    DELETE = auto()
    RENAME = auto()

class CacheOperation(Enum):
    """Types of cache operations that can be performed."""
    GET = auto()
    SET = auto()
    DELETE = auto()
    CLEAR = auto()
    REFRESH = auto()

class TaskPriority(Enum):
    """Priority levels for async tasks."""
    LOW = auto()
    NORMAL = auto()
    HIGH = auto()
    CRITICAL = auto()

# Additional data models for resource management
@dataclass
class ResourceUsage:
    """Resource usage information."""
    cpu_percent: float
    memory_bytes: int
    memory_percent: float
    disk_bytes: int
    disk_percent: float
    network_sent_bytes: int
    network_recv_bytes: int
    timestamp: datetime = field(default_factory=datetime.now)
    
    def is_resource_critical(self, threshold: float = 95.0) -> bool:
        """Check if any resource usage exceeds critical threshold."""
        return (
            self.cpu_percent >= threshold or
            self.memory_percent >= threshold or
            self.disk_percent >= threshold
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceUsage':
        """Create from dictionary."""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)

# Additional data models for async operations
@dataclass
class TaskInfo:
    """Information about an async task."""
    task_id: str
    name: str
    priority: TaskPriority
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"
    error: Optional[str] = None
    
    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate task duration if completed."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    @property
    def is_running(self) -> bool:
        """Check if task is currently running."""
        return self.started_at is not None and self.completed_at is None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            'task_id': self.task_id,
            'name': self.name,
            'priority': self.priority.name,
            'created_at': self.created_at.isoformat(),
            'status': self.status
        }
        
        if self.started_at:
            result['started_at'] = self.started_at.isoformat()
        if self.completed_at:
            result['completed_at'] = self.completed_at.isoformat()
        if self.error:
            result['error'] = self.error
            
        return result