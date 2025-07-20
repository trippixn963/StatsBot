"""
Custom exception classes for better error categorization.

This module defines a hierarchy of custom exceptions that provide
better error handling and categorization throughout the StatsBot application.
Each exception class includes contextual information to aid in debugging
and provides consistent error reporting interfaces.
"""

from typing import Optional, Any, Dict


class StatsBotError(Exception):
    """
    Base exception class for all StatsBot-related errors.
    
    This is the root exception that all other custom exceptions inherit from,
    providing a common interface for error handling.
    
    Attributes:
        message (str): Human-readable error message
        error_code (str): Machine-readable error code for categorization
        context (Dict[str, Any]): Additional context information
    """
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.context = context or {}
    
    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging."""
        return {
            'error_type': self.__class__.__name__,
            'error_code': self.error_code,
            'message': self.message,
            'context': self.context
        }


class ConfigurationError(StatsBotError):
    """
    Raised when there are configuration-related errors.
    
    This includes missing environment variables, invalid configuration values,
    or configuration validation failures. The error provides detailed context
    about what went wrong and how to fix it.
    """
    
    def __init__(
        self, 
        message: str, 
        missing_keys: Optional[list] = None,
        invalid_values: Optional[Dict[str, Any]] = None,
        validation_errors: Optional[list] = None,
        env_file_path: Optional[str] = None
    ):
        context = {}
        if missing_keys:
            context['missing_keys'] = missing_keys
        if invalid_values:
            context['invalid_values'] = invalid_values
        if validation_errors:
            context['validation_errors'] = validation_errors
        if env_file_path:
            context['env_file_path'] = env_file_path
            
        super().__init__(message, "CONFIG_ERROR", context)
        self.missing_keys = missing_keys or []
        self.invalid_values = invalid_values or {}
        self.validation_errors = validation_errors or []
        self.env_file_path = env_file_path
        
    def get_troubleshooting_message(self) -> str:
        """
        Get a detailed troubleshooting message for this configuration error.
        
        Returns:
            str: Formatted troubleshooting message with guidance on how to fix the issue
        """
        message = [f"Configuration Error: {self.message}"]
        
        if self.missing_keys:
            message.append("\nMissing required environment variables:")
            for key in self.missing_keys:
                message.append(f"  - {key}")
            message.append("\nPlease add these variables to your .env file.")
            
        if self.invalid_values:
            message.append("\nInvalid environment variable values:")
            for key, value in self.invalid_values.items():
                message.append(f"  - {key}: {value}")
            message.append("\nPlease check the data types and formats of these variables.")
            
        if self.validation_errors:
            message.append("\nConfiguration validation errors:")
            for error in self.validation_errors:
                message.append(f"  - {error}")
                
        if self.env_file_path:
            message.append(f"\nEnvironment file path: {self.env_file_path}")
            
        message.append("\nFor more help, see the configuration documentation or run the troubleshooting command.")
        
        return "\n".join(message)


class DiscordAPIError(StatsBotError):
    """
    Raised when Discord API operations fail.
    
    This includes rate limits, permission errors, network failures,
    and other Discord-specific errors.
    """
    
    def __init__(
        self, 
        message: str, 
        status_code: Optional[int] = None,
        retry_after: Optional[float] = None,
        operation: Optional[str] = None
    ):
        context = {}
        if status_code:
            context['status_code'] = status_code
        if retry_after:
            context['retry_after'] = retry_after
        if operation:
            context['operation'] = operation
            
        super().__init__(message, "DISCORD_API_ERROR", context)
        self.status_code = status_code
        self.retry_after = retry_after
        self.operation = operation


class DataPersistenceError(StatsBotError):
    """
    Raised when data persistence operations fail.
    
    This includes file I/O errors, JSON serialization/deserialization errors,
    and data corruption issues.
    """
    
    def __init__(
        self, 
        message: str, 
        file_path: Optional[str] = None,
        operation: Optional[str] = None,
        original_error: Optional[Exception] = None
    ):
        context = {}
        if file_path:
            context['file_path'] = file_path
        if operation:
            context['operation'] = operation
        if original_error:
            context['original_error'] = str(original_error)
            context['original_error_type'] = type(original_error).__name__
            
        super().__init__(message, "DATA_PERSISTENCE_ERROR", context)
        self.file_path = file_path
        self.operation = operation
        self.original_error = original_error


class ResourceError(StatsBotError):
    """
    Raised when resource management operations fail.
    
    This includes memory allocation errors, resource cleanup failures,
    and resource limit exceeded errors.
    """
    
    def __init__(
        self, 
        message: str, 
        resource_type: Optional[str] = None,
        current_usage: Optional[float] = None,
        limit: Optional[float] = None
    ):
        context = {}
        if resource_type:
            context['resource_type'] = resource_type
        if current_usage is not None:
            context['current_usage'] = current_usage
        if limit is not None:
            context['limit'] = limit
            
        super().__init__(message, "RESOURCE_ERROR", context)
        self.resource_type = resource_type
        self.current_usage = current_usage
        self.limit = limit


class ResourceExhaustionError(ResourceError):
    """
    Raised when a resource is exhausted or exceeds critical thresholds.
    
    This includes memory exhaustion, disk space exhaustion, and other
    resource limit exceeded scenarios that require immediate attention.
    """
    
    def __init__(
        self, 
        message: str, 
        resource_type: str,
        current_usage: float,
        limit: float,
        recommended_action: Optional[str] = None
    ):
        super().__init__(message, resource_type, current_usage, limit)
        self.error_code = "RESOURCE_EXHAUSTION_ERROR"
        self.recommended_action = recommended_action
        
        if recommended_action:
            self.context['recommended_action'] = recommended_action


class ValidationError(StatsBotError):
    """
    Raised when data validation fails.
    
    This includes invalid input data, schema validation failures,
    and constraint violations.
    """
    
    def __init__(
        self, 
        message: str, 
        field_name: Optional[str] = None,
        expected_type: Optional[str] = None,
        actual_value: Optional[Any] = None
    ):
        context = {}
        if field_name:
            context['field_name'] = field_name
        if expected_type:
            context['expected_type'] = expected_type
        if actual_value is not None:
            context['actual_value'] = str(actual_value)
            context['actual_type'] = type(actual_value).__name__
            
        super().__init__(message, "VALIDATION_ERROR", context)
        self.field_name = field_name
        self.expected_type = expected_type
        self.actual_value = actual_value


class CacheError(StatsBotError):
    """
    Raised when cache operations fail.
    
    This includes cache miss errors, cache invalidation failures,
    and cache storage errors.
    """
    
    def __init__(
        self, 
        message: str, 
        cache_key: Optional[str] = None,
        operation: Optional[str] = None
    ):
        context = {}
        if cache_key:
            context['cache_key'] = cache_key
        if operation:
            context['operation'] = operation
            
        super().__init__(message, "CACHE_ERROR", context)
        self.cache_key = cache_key
        self.operation = operation


class CircuitBreakerError(StatsBotError):
    """
    Raised when circuit breaker is open and operations are blocked.
    
    This indicates that a service or operation has failed repeatedly
    and the circuit breaker has opened to prevent further failures.
    """
    
    def __init__(
        self, 
        message: str, 
        service_name: Optional[str] = None,
        failure_count: Optional[int] = None,
        next_retry_time: Optional[float] = None
    ):
        context = {}
        if service_name:
            context['service_name'] = service_name
        if failure_count is not None:
            context['failure_count'] = failure_count
        if next_retry_time is not None:
            context['next_retry_time'] = next_retry_time
            
        super().__init__(message, "CIRCUIT_BREAKER_ERROR", context)
        self.service_name = service_name
        self.failure_count = failure_count
        self.next_retry_time = next_retry_time


class AsyncOperationError(StatsBotError):
    """
    Raised when asynchronous operations fail.
    
    This includes task cancellation errors, timeout errors,
    and concurrency-related issues.
    """
    
    def __init__(
        self, 
        message: str, 
        operation_name: Optional[str] = None,
        task_id: Optional[str] = None,
        timeout: Optional[float] = None,
        was_cancelled: bool = False
    ):
        context = {}
        if operation_name:
            context['operation_name'] = operation_name
        if task_id:
            context['task_id'] = task_id
        if timeout is not None:
            context['timeout'] = timeout
        context['was_cancelled'] = was_cancelled
            
        super().__init__(message, "ASYNC_OPERATION_ERROR", context)
        self.operation_name = operation_name
        self.task_id = task_id
        self.timeout = timeout
        self.was_cancelled = was_cancelled


class RateLimitError(StatsBotError):
    """
    Raised when rate limits are encountered.
    
    This includes Discord API rate limits, third-party API rate limits,
    and internal rate limiting mechanisms.
    """
    
    def __init__(
        self, 
        message: str, 
        retry_after: Optional[float] = None,
        endpoint: Optional[str] = None,
        limit: Optional[int] = None,
        remaining: Optional[int] = None
    ):
        context = {}
        if retry_after is not None:
            context['retry_after'] = retry_after
        if endpoint:
            context['endpoint'] = endpoint
        if limit is not None:
            context['limit'] = limit
        if remaining is not None:
            context['remaining'] = remaining
            
        super().__init__(message, "RATE_LIMIT_ERROR", context)
        self.retry_after = retry_after
        self.endpoint = endpoint
        self.limit = limit
        self.remaining = remaining


class ServiceError(StatsBotError):
    """
    Raised when service operations fail.
    
    This includes service initialization errors, service dependency errors,
    and service state errors.
    """
    
    def __init__(
        self, 
        message: str, 
        service_name: Optional[str] = None,
        operation: Optional[str] = None,
        dependency: Optional[str] = None
    ):
        context = {}
        if service_name:
            context['service_name'] = service_name
        if operation:
            context['operation'] = operation
        if dependency:
            context['dependency'] = dependency
            
        super().__init__(message, "SERVICE_ERROR", context)
        self.service_name = service_name
        self.operation = operation
        self.dependency = dependency


class NetworkError(StatsBotError):
    """
    Raised when network operations fail.
    
    This includes connection errors, timeout errors, DNS resolution errors,
    and other network-related issues.
    """
    
    def __init__(
        self, 
        message: str, 
        host: Optional[str] = None,
        port: Optional[int] = None,
        timeout: Optional[float] = None,
        retry_count: Optional[int] = None
    ):
        context = {}
        if host:
            context['host'] = host
        if port is not None:
            context['port'] = port
        if timeout is not None:
            context['timeout'] = timeout
        if retry_count is not None:
            context['retry_count'] = retry_count
            
        super().__init__(message, "NETWORK_ERROR", context)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retry_count = retry_count


class LifecycleError(StatsBotError):
    """
    Raised when lifecycle operations fail.
    
    This includes startup errors, shutdown errors, and state transition errors.
    """
    
    def __init__(
        self, 
        message: str, 
        phase: Optional[str] = None,
        component: Optional[str] = None,
        current_state: Optional[str] = None,
        target_state: Optional[str] = None
    ):
        context = {}
        if phase:
            context['phase'] = phase
        if component:
            context['component'] = component
        if current_state:
            context['current_state'] = current_state
        if target_state:
            context['target_state'] = target_state
            
        super().__init__(message, "LIFECYCLE_ERROR", context)
        self.phase = phase
        self.component = component
        self.current_state = current_state
        self.target_state = target_state


class MonitoringError(ServiceError):
    """
    Raised when monitoring operations fail.
    
    This includes heartbeat update failures, metrics collection errors,
    and monitoring service state errors.
    """
    
    def __init__(
        self, 
        message: str, 
        operation: Optional[str] = None,
        metrics_type: Optional[str] = None,
        channel_id: Optional[int] = None
    ):
        context = {}
        if metrics_type:
            context['metrics_type'] = metrics_type
        if channel_id is not None:
            context['channel_id'] = channel_id
            
        super().__init__(message, "monitoring", operation, None)
        self.error_code = "MONITORING_ERROR"
        self.metrics_type = metrics_type
        self.channel_id = channel_id