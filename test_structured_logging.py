"""
Test script for the structured logging system.

This script demonstrates the usage of the structured logging system
with various features like contextual logging, performance timing,
and log rotation.
"""

import time
from src.utils.logging import StructuredLogger, timed
from src.types.models import LogLevel


class LoggingDemo:
    """Demo class to showcase structured logging features."""
    
    def __init__(self):
        """Initialize the demo with a structured logger."""
        self.logger = StructuredLogger(
            name="demo",
            level=LogLevel.DEBUG,
            max_memory_entries=100,
            retention_days=7
        )
        
    @timed("expensive_operation")
    def expensive_operation(self, iterations: int) -> int:
        """
        Simulate an expensive operation and log its performance.
        
        Args:
            iterations: Number of iterations
            
        Returns:
            Result of the operation
        """
        self.logger.info(f"Starting expensive operation with {iterations} iterations")
        
        result = 0
        for i in range(iterations):
            result += i
            time.sleep(0.001)  # Simulate work
            
        self.logger.info(f"Completed expensive operation with result {result}")
        return result
        
    def demonstrate_context_logging(self) -> None:
        """Demonstrate contextual logging."""
        # Create a context logger for a specific user
        user_logger = self.logger.with_context(user_id="123", username="test_user")
        
        # Log with the context
        user_logger.info("User logged in")
        
        # Add more context
        session_logger = user_logger.with_context(session_id="abc123")
        session_logger.info("User started a new session")
        
        # Log an error with context
        try:
            raise ValueError("Something went wrong")
        except Exception as e:
            session_logger.error("Error during user session", error=e)
            
    def demonstrate_log_levels(self) -> None:
        """Demonstrate different log levels."""
        self.logger.debug("This is a debug message")
        self.logger.info("This is an info message")
        self.logger.warning("This is a warning message")
        self.logger.error("This is an error message")
        self.logger.critical("This is a critical message")
        
    def demonstrate_performance_logging(self) -> None:
        """Demonstrate performance logging."""
        # Direct performance logging
        start_time = time.time()
        time.sleep(0.1)  # Simulate work
        duration_ms = (time.time() - start_time) * 1000
        self.logger.performance("manual_operation", duration_ms)
        
        # Using the timed decorator
        self.expensive_operation(100)
        
    def run_demo(self) -> None:
        """Run the full logging demonstration."""
        self.logger.info("Starting logging demonstration")
        
        self.demonstrate_log_levels()
        self.demonstrate_context_logging()
        self.demonstrate_performance_logging()
        
        # Show recent logs
        recent_logs = self.logger.get_recent_logs(limit=5)
        print(f"\nRecent logs ({len(recent_logs)}):")
        for log in recent_logs:
            print(f"- {log.timestamp}: {log.message}")
            
        self.logger.info("Logging demonstration completed")


if __name__ == "__main__":
    demo = LoggingDemo()
    demo.run_demo()