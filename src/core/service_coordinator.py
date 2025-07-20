"""
Service coordinator for managing service lifecycle and dependencies.

This module provides a coordinator for managing the lifecycle of multiple services,
ensuring proper startup and shutdown sequencing based on dependencies.
"""

import asyncio
import logging
from enum import Enum
from typing import Dict, List, Set, Optional, Any, Callable, Awaitable, TypeVar, Generic, Union

from ..types.models import ServiceStatus
from ..utils.logging.structured_logger import StructuredLogger
from .exceptions import LifecycleError, ServiceError

# Type for service objects
T = TypeVar('T')


class ServiceCoordinator:
    """
    Coordinates the lifecycle of multiple services with dependency management.
    
    This class ensures that services are started and stopped in the correct order
    based on their dependencies, preventing issues with services that depend on
    each other.
    
    Attributes:
        logger: Logger instance
        services: Dictionary of registered services
        dependencies: Dictionary mapping service names to their dependencies
        dependents: Dictionary mapping service names to services that depend on them
        startup_order: List of service names in dependency order for startup
        shutdown_order: List of service names in reverse dependency order for shutdown
    """
    
    def __init__(self, logger: Optional[StructuredLogger] = None):
        """
        Initialize a new service coordinator.
        
        Args:
            logger: Logger instance (creates one if None)
        """
        self.logger = logger or StructuredLogger("service_coordinator")
        self.services: Dict[str, Any] = {}
        self.dependencies: Dict[str, Set[str]] = {}
        self.dependents: Dict[str, Set[str]] = {}
        self.startup_order: List[str] = []
        self.shutdown_order: List[str] = []
        self._status_cache: Dict[str, ServiceStatus] = {}
    
    def register_service(
        self, 
        name: str, 
        service: Any, 
        dependencies: Optional[List[str]] = None
    ) -> None:
        """
        Register a service with the coordinator.
        
        Args:
            name: Name of the service
            service: Service instance
            dependencies: List of service names this service depends on
            
        Raises:
            ValueError: If service name is already registered
            ValueError: If a dependency doesn't exist
        """
        if name in self.services:
            raise ValueError(f"Service '{name}' is already registered")
            
        # Register the service
        self.services[name] = service
        
        # Initialize dependency tracking
        deps = set(dependencies or [])
        self.dependencies[name] = deps
        
        # Validate dependencies
        for dep in deps:
            if dep not in self.services and dep != name:
                raise ValueError(f"Service '{name}' depends on unknown service '{dep}'")
        
        # Update dependents tracking
        for dep in deps:
            if dep not in self.dependents:
                self.dependents[dep] = set()
            self.dependents[dep].add(name)
            
        # Update dependency order
        self._update_dependency_order()
        
        self.logger.info(
            f"Registered service '{name}'",
            service=name,
            dependencies=list(deps)
        )
    
    def _update_dependency_order(self) -> None:
        """
        Update the startup and shutdown order based on dependencies.
        
        This uses a topological sort to determine the correct order.
        
        Raises:
            LifecycleError: If there is a circular dependency
        """
        # Reset orders
        self.startup_order = []
        self.shutdown_order = []
        
        # Copy dependencies for processing
        remaining_deps = {name: set(deps) for name, deps in self.dependencies.items()}
        
        # Process services with no dependencies first
        no_deps = [name for name, deps in remaining_deps.items() if not deps]
        
        # Topological sort
        while no_deps:
            # Get next service with no dependencies
            name = no_deps.pop(0)
            self.startup_order.append(name)
            
            # Update dependencies of services that depend on this one
            for dependent in self.dependents.get(name, set()):
                if dependent in remaining_deps:
                    remaining_deps[dependent].discard(name)
                    if not remaining_deps[dependent]:
                        no_deps.append(dependent)
        
        # Check for circular dependencies
        if any(remaining_deps.values()):
            circular = [name for name, deps in remaining_deps.items() if deps]
            raise LifecycleError(
                f"Circular dependency detected among services: {', '.join(circular)}",
                phase="initialization",
                component="service_coordinator"
            )
            
        # Shutdown order is reverse of startup order
        self.shutdown_order = list(reversed(self.startup_order))
        
        self.logger.debug(
            "Updated service dependency order",
            startup_order=self.startup_order,
            shutdown_order=self.shutdown_order
        )
    
    async def start_services(self) -> None:
        """
        Start all registered services in dependency order.
        
        This method ensures that services are started in the correct order,
        with dependencies started before the services that depend on them.
        
        Raises:
            ServiceError: If a service fails to start
        """
        self.logger.info("Starting services in dependency order")
        
        for name in self.startup_order:
            service = self.services[name]
            
            try:
                self.logger.info(f"Starting service '{name}'")
                
                # Check if service has a start method
                if hasattr(service, 'start') and callable(service.start):
                    await service.start()
                    
                self.logger.info(f"Service '{name}' started successfully")
                
            except Exception as e:
                self.logger.error(
                    f"Failed to start service '{name}'",
                    error=str(e),
                    service=name,
                    exc_info=True
                )
                raise ServiceError(
                    f"Failed to start service '{name}': {str(e)}",
                    service_name=name,
                    operation="start"
                ) from e
    
    async def stop_services(self) -> None:
        """
        Stop all registered services in reverse dependency order.
        
        This method ensures that services are stopped in the correct order,
        with dependent services stopped before the services they depend on.
        """
        self.logger.info("Stopping services in reverse dependency order")
        
        errors = []
        
        for name in self.shutdown_order:
            service = self.services[name]
            
            try:
                self.logger.info(f"Stopping service '{name}'")
                
                # Check if service has a stop method
                if hasattr(service, 'stop') and callable(service.stop):
                    await service.stop()
                    
                self.logger.info(f"Service '{name}' stopped successfully")
                
            except Exception as e:
                self.logger.error(
                    f"Error stopping service '{name}'",
                    error=str(e),
                    service=name,
                    exc_info=True
                )
                errors.append((name, str(e)))
        
        if errors:
            error_msgs = [f"'{name}': {error}" for name, error in errors]
            self.logger.error(
                f"Errors occurred while stopping services: {', '.join(error_msgs)}"
            )
    
    def get_service(self, name: str) -> Any:
        """
        Get a registered service by name.
        
        Args:
            name: Name of the service
            
        Returns:
            The service instance
            
        Raises:
            KeyError: If the service is not registered
        """
        if name not in self.services:
            raise KeyError(f"Service '{name}' is not registered")
        return self.services[name]
    
    def get_service_status(self, name: str) -> ServiceStatus:
        """
        Get the status of a service.
        
        Args:
            name: Name of the service
            
        Returns:
            Current status of the service
            
        Raises:
            KeyError: If the service is not registered
        """
        if name not in self.services:
            raise KeyError(f"Service '{name}' is not registered")
            
        service = self.services[name]
        
        # Check if service has a status property or method
        if hasattr(service, 'status'):
            if callable(service.status):
                return service.status()
            else:
                return service.status
        
        # Default to UNKNOWN if status can't be determined
        return ServiceStatus.UNKNOWN
    
    def get_all_service_statuses(self) -> Dict[str, ServiceStatus]:
        """
        Get the status of all registered services.
        
        Returns:
            Dictionary mapping service names to their current status
        """
        return {name: self.get_service_status(name) for name in self.services}
    
    def is_service_running(self, name: str) -> bool:
        """
        Check if a service is running.
        
        Args:
            name: Name of the service
            
        Returns:
            True if the service is running, False otherwise
            
        Raises:
            KeyError: If the service is not registered
        """
        status = self.get_service_status(name)
        return status == ServiceStatus.RUNNING
    
    def are_all_services_running(self) -> bool:
        """
        Check if all services are running.
        
        Returns:
            True if all services are running, False otherwise
        """
        for name in self.services:
            if not self.is_service_running(name):
                return False
        return True