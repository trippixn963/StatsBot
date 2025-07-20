#!/usr/bin/env python3
"""
StatsBot Performance Benchmarking Script.

This script performs comprehensive performance benchmarking and validation
to ensure all optimizations are working correctly and provide measurable
improvements over the original implementation.

Usage:
    python scripts/benchmark.py [--verbose] [--output results.json]
"""

import asyncio
import json
import time
import argparse
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from utils.performance import PerformanceMonitor, performance_context, get_memory_stats
from utils.memory_optimizer import (
    MemoryEfficientStats, 
    CircularBuffer, 
    TimeBasedCache,
    StreamProcessor,
    get_memory_stats as get_memory_usage
)
from utils.network_optimizer import (
    ConnectionPool,
    DiscordAPIBatcher,
    AdaptivePoller,
    APIRequest
)
from utils.config_validator import ConfigValidator


@dataclass
class BenchmarkResult:
    """Result of a benchmark test."""
    name: str
    duration_ms: float
    memory_usage_mb: float
    memory_delta_mb: float
    success: bool
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class BenchmarkSuite:
    """Complete benchmark suite results."""
    timestamp: str
    total_duration_ms: float
    tests_run: int
    tests_passed: int
    tests_failed: int
    results: List[BenchmarkResult]
    system_info: Dict[str, Any]
    performance_summary: Dict[str, Any]


class StatsBot Benchmarker:
    """
    Comprehensive benchmarking system for StatsBot optimizations.
    
    This class runs various performance tests to validate that optimizations
    provide measurable improvements in memory usage, response time, and
    overall system performance.
    """
    
    def __init__(self, verbose: bool = False):
        """
        Initialize benchmarker.
        
        Args:
            verbose: Enable verbose output during benchmarking
        """
        self.verbose = verbose
        self.results: List[BenchmarkResult] = []
        self.monitor = PerformanceMonitor()
        
        if verbose:
            print("🚀 StatsBot Performance Benchmarker")
            print("=" * 50)
    
    def log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
    
    async def run_all_benchmarks(self) -> BenchmarkSuite:
        """
        Run complete benchmark suite.
        
        Returns:
            BenchmarkSuite containing all benchmark results
        """
        start_time = time.time()
        self.log("Starting comprehensive benchmark suite...")
        
        # Memory optimization benchmarks
        await self._benchmark_memory_optimizations()
        
        # Performance monitoring benchmarks
        await self._benchmark_performance_monitoring()
        
        # Network optimization benchmarks
        await self._benchmark_network_optimizations()
        
        # Configuration validation benchmarks
        await self._benchmark_config_validation()
        
        # Integration benchmarks
        await self._benchmark_integration_scenarios()
        
        total_duration = (time.time() - start_time) * 1000
        
        # Generate summary
        tests_passed = sum(1 for r in self.results if r.success)
        tests_failed = len(self.results) - tests_passed
        
        suite = BenchmarkSuite(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_duration_ms=total_duration,
            tests_run=len(self.results),
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            results=self.results,
            system_info=self._get_system_info(),
            performance_summary=self._get_performance_summary()
        )
        
        self.log(f"✅ Benchmark suite completed in {total_duration:.2f}ms")
        self.log(f"📊 Results: {tests_passed} passed, {tests_failed} failed")
        
        return suite
    
    async def _benchmark_memory_optimizations(self):
        """Benchmark memory optimization features."""
        self.log("🧠 Benchmarking memory optimizations...")
        
        # Test CircularBuffer performance
        await self._run_benchmark(
            "circular_buffer_operations",
            self._test_circular_buffer_performance,
            {"buffer_size": 1000, "operations": 10000}
        )
        
        # Test TimeBasedCache performance
        await self._run_benchmark(
            "time_based_cache_operations",
            self._test_time_based_cache_performance,
            {"cache_size": 1000, "operations": 5000}
        )
        
        # Test MemoryEfficientStats
        await self._run_benchmark(
            "memory_efficient_stats",
            self._test_memory_efficient_stats,
            {"events": 1000}
        )
        
        # Test StreamProcessor
        await self._run_benchmark(
            "stream_processor",
            self._test_stream_processor,
            {"items": 10000, "batch_size": 100}
        )
    
    async def _benchmark_performance_monitoring(self):
        """Benchmark performance monitoring overhead."""
        self.log("📊 Benchmarking performance monitoring...")
        
        # Test timing decorator overhead
        await self._run_benchmark(
            "timing_decorator_overhead",
            self._test_timing_decorator_overhead,
            {"iterations": 1000}
        )
        
        # Test memory monitoring overhead
        await self._run_benchmark(
            "memory_monitoring_overhead",
            self._test_memory_monitoring_overhead,
            {"iterations": 500}
        )
    
    async def _benchmark_network_optimizations(self):
        """Benchmark network optimization features."""
        self.log("🌐 Benchmarking network optimizations...")
        
        # Test connection pool efficiency
        await self._run_benchmark(
            "connection_pool_efficiency",
            self._test_connection_pool,
            {"connections": 50}
        )
        
        # Test API batcher performance
        await self._run_benchmark(
            "api_batcher_performance",
            self._test_api_batcher,
            {"requests": 100, "batch_size": 10}
        )
        
        # Test adaptive poller
        await self._run_benchmark(
            "adaptive_poller",
            self._test_adaptive_poller,
            {"activities": 50}
        )
    
    async def _benchmark_config_validation(self):
        """Benchmark configuration validation performance."""
        self.log("⚙️ Benchmarking configuration validation...")
        
        await self._run_benchmark(
            "config_validation_performance",
            self._test_config_validation,
            {"validations": 100}
        )
    
    async def _benchmark_integration_scenarios(self):
        """Benchmark realistic integration scenarios."""
        self.log("🔧 Benchmarking integration scenarios...")
        
        # Test complete stats processing workflow
        await self._run_benchmark(
            "stats_processing_workflow",
            self._test_stats_workflow,
            {"members": 1000, "events": 500}
        )
        
        # Test concurrent operations
        await self._run_benchmark(
            "concurrent_operations",
            self._test_concurrent_operations,
            {"concurrent_tasks": 20}
        )
    
    async def _run_benchmark(self, name: str, test_func: callable, params: Dict[str, Any]):
        """
        Run a single benchmark test.
        
        Args:
            name: Test name
            test_func: Test function to execute
            params: Test parameters
        """
        self.log(f"  Running {name}...")
        
        # Measure initial memory
        initial_memory = get_memory_usage()
        start_time = time.perf_counter()
        
        try:
            # Run the test
            result = await test_func(**params)
            
            # Measure final state
            end_time = time.perf_counter()
            final_memory = get_memory_usage()
            
            duration_ms = (end_time - start_time) * 1000
            memory_delta = final_memory.rss_mb - initial_memory.rss_mb
            
            benchmark_result = BenchmarkResult(
                name=name,
                duration_ms=duration_ms,
                memory_usage_mb=final_memory.rss_mb,
                memory_delta_mb=memory_delta,
                success=True,
                metadata={
                    "params": params,
                    "result": result if isinstance(result, (int, float, str, bool, dict, list)) else str(result)
                }
            )
            
            self.log(f"    ✅ {name}: {duration_ms:.2f}ms, {memory_delta:+.2f}MB")
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            final_memory = get_memory_usage()
            memory_delta = final_memory.rss_mb - initial_memory.rss_mb
            
            benchmark_result = BenchmarkResult(
                name=name,
                duration_ms=duration_ms,
                memory_usage_mb=final_memory.rss_mb,
                memory_delta_mb=memory_delta,
                success=False,
                error_message=str(e),
                metadata={"params": params}
            )
            
            self.log(f"    ❌ {name}: FAILED - {str(e)}")
        
        self.results.append(benchmark_result)
    
    async def _test_circular_buffer_performance(self, buffer_size: int, operations: int) -> Dict[str, Any]:
        """Test CircularBuffer performance."""
        buffer = CircularBuffer(maxsize=buffer_size)
        
        # Test append operations
        for i in range(operations):
            buffer.append(f"item_{i}")
        
        # Test retrieval operations
        recent_items = buffer.get_recent(100)
        
        return {
            "buffer_size": len(buffer),
            "total_added": buffer.total_added,
            "recent_items_count": len(recent_items)
        }
    
    async def _test_time_based_cache_performance(self, cache_size: int, operations: int) -> Dict[str, Any]:
        """Test TimeBasedCache performance."""
        cache = TimeBasedCache(max_size=cache_size, default_ttl=60.0)
        
        # Test set operations
        for i in range(operations):
            cache.set(f"key_{i}", f"value_{i}")
        
        # Test get operations
        hits = 0
        for i in range(min(operations, 1000)):
            if cache.get(f"key_{i}") is not None:
                hits += 1
        
        return {
            "cache_size": cache.size(),
            "hit_rate": hits / min(operations, 1000) * 100
        }
    
    async def _test_memory_efficient_stats(self, events: int) -> Dict[str, Any]:
        """Test MemoryEfficientStats performance."""
        stats = MemoryEfficientStats()
        
        # Add member events
        for i in range(events):
            event_type = ["join", "leave", "ban"][i % 3]
            stats.add_member_event(event_type, 1000000 + i, f"User{i}")
        
        # Add performance metrics
        for i in range(events // 2):
            stats.add_performance_metric(f"metric_{i % 10}", i * 0.1)
        
        memory_usage = stats.get_memory_usage()
        
        return {
            "member_events": memory_usage["member_events_count"],
            "performance_metrics": memory_usage["performance_metrics_count"],
            "estimated_memory_mb": memory_usage["estimated_memory_mb"]
        }
    
    async def _test_stream_processor(self, items: int, batch_size: int) -> Dict[str, Any]:
        """Test StreamProcessor performance."""
        processor = StreamProcessor(batch_size=batch_size)
        
        # Create data stream
        def data_generator():
            for i in range(items):
                yield {"id": i, "data": f"item_{i}"}
        
        processed_count = 0
        
        def process_batch(batch):
            nonlocal processed_count
            processed_count += len(batch)
        
        total_processed = processor.process_member_data_stream(
            data_generator(), 
            process_batch
        )
        
        return {
            "total_processed": total_processed,
            "processed_count": processed_count,
            "expected_items": items
        }
    
    async def _test_timing_decorator_overhead(self, iterations: int) -> Dict[str, Any]:
        """Test timing decorator overhead."""
        monitor = PerformanceMonitor()
        
        @monitor.timing_decorator(category="benchmark")
        def decorated_function(x: int) -> int:
            return x * 2
        
        def plain_function(x: int) -> int:
            return x * 2
        
        # Benchmark decorated function
        start_time = time.perf_counter()
        for i in range(iterations):
            decorated_function(i)
        decorated_time = time.perf_counter() - start_time
        
        # Benchmark plain function
        start_time = time.perf_counter()
        for i in range(iterations):
            plain_function(i)
        plain_time = time.perf_counter() - start_time
        
        overhead_percent = ((decorated_time - plain_time) / plain_time) * 100
        
        monitor.shutdown()
        
        return {
            "decorated_time_ms": decorated_time * 1000,
            "plain_time_ms": plain_time * 1000,
            "overhead_percent": overhead_percent
        }
    
    async def _test_memory_monitoring_overhead(self, iterations: int) -> Dict[str, Any]:
        """Test memory monitoring overhead."""
        # Test with memory monitoring
        start_time = time.perf_counter()
        for i in range(iterations):
            with performance_context(f"test_{i}", include_memory=True):
                result = sum(range(100))
        memory_time = time.perf_counter() - start_time
        
        # Test without memory monitoring  
        start_time = time.perf_counter()
        for i in range(iterations):
            with performance_context(f"test_{i}", include_memory=False):
                result = sum(range(100))
        no_memory_time = time.perf_counter() - start_time
        
        overhead_percent = ((memory_time - no_memory_time) / no_memory_time) * 100
        
        return {
            "with_memory_ms": memory_time * 1000,
            "without_memory_ms": no_memory_time * 1000,
            "overhead_percent": overhead_percent
        }
    
    async def _test_connection_pool(self, connections: int) -> Dict[str, Any]:
        """Test connection pool efficiency."""
        pool = ConnectionPool(max_connections=connections)
        
        start_time = time.perf_counter()
        
        # Simulate multiple connection requests
        tasks = []
        for i in range(connections):
            task = asyncio.create_task(self._simulate_connection(pool, i))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = sum(1 for r in results if not isinstance(r, Exception))
        
        end_time = time.perf_counter()
        
        await pool.close()
        
        return {
            "total_connections": connections,
            "successful_connections": successful,
            "duration_ms": (end_time - start_time) * 1000,
            "success_rate": successful / connections * 100
        }
    
    async def _simulate_connection(self, pool: ConnectionPool, request_id: int) -> str:
        """Simulate a connection request."""
        session = await pool.get_session()
        await asyncio.sleep(0.001)  # Simulate work
        return f"request_{request_id}_completed"
    
    async def _test_api_batcher(self, requests: int, batch_size: int) -> Dict[str, Any]:
        """Test API batcher performance."""
        batcher = DiscordAPIBatcher(batch_size=batch_size, batch_timeout=0.1)
        await batcher.start()
        
        # Queue multiple requests
        start_time = time.perf_counter()
        
        tasks = []
        for i in range(requests):
            request = APIRequest(
                endpoint=f"/test/{i % 10}",
                method="GET",
                data={"id": i}
            )
            task = asyncio.create_task(batcher.queue_request(request))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = sum(1 for r in results if not isinstance(r, Exception))
        
        end_time = time.perf_counter()
        
        await batcher.stop()
        
        return {
            "total_requests": requests,
            "successful_requests": successful,
            "duration_ms": (end_time - start_time) * 1000,
            "requests_per_second": requests / (end_time - start_time)
        }
    
    async def _test_adaptive_poller(self, activities: int) -> Dict[str, Any]:
        """Test adaptive poller performance."""
        poller = AdaptivePoller(
            base_interval=10.0,
            min_interval=1.0,
            max_interval=60.0,
            activity_threshold=5
        )
        
        intervals = []
        
        # Simulate varying activity levels
        for i in range(activities):
            # High activity period
            for _ in range(10):
                poller.record_activity()
            
            interval = poller.get_next_interval()
            intervals.append(interval)
            
            await asyncio.sleep(0.001)  # Small delay
        
        return {
            "total_activities": activities,
            "intervals_recorded": len(intervals),
            "avg_interval": statistics.mean(intervals),
            "min_interval": min(intervals),
            "max_interval": max(intervals)
        }
    
    async def _test_config_validation(self, validations: int) -> Dict[str, Any]:
        """Test configuration validation performance."""
        validator = ConfigValidator()
        
        # Test configuration validation speed
        start_time = time.perf_counter()
        
        test_config = {
            'BOT_TOKEN': 'MTxxxxxxxxx.xxxxxx.xxxxxxxxxxxxxxxxxxxxxxx',
            'MEMBER_COUNT_CHANNEL_ID': 1234567890123456789,
            'ONLINE_COUNT_CHANNEL_ID': 1234567890123456790,
            'BAN_COUNT_CHANNEL_ID': 1234567890123456791,
            'HEARTBEAT_CHANNEL_ID': 1234567890123456792,
            'STATS_CHANNEL_ID': 1234567890123456793,
            'GUILD_ID': 1234567890123456794
        }
        
        for i in range(validations):
            errors = validator.validate_runtime_config(test_config)
        
        end_time = time.perf_counter()
        
        return {
            "validations": validations,
            "duration_ms": (end_time - start_time) * 1000,
            "validations_per_second": validations / (end_time - start_time),
            "has_errors": len(errors) > 0
        }
    
    async def _test_stats_workflow(self, members: int, events: int) -> Dict[str, Any]:
        """Test complete stats processing workflow."""
        stats = MemoryEfficientStats()
        
        start_time = time.perf_counter()
        
        # Simulate member events
        for i in range(events):
            event_type = ["join", "leave", "ban"][i % 3]
            member_id = 1000000 + (i % members)
            username = f"User{member_id}"
            
            stats.add_member_event(event_type, member_id, username)
        
        # Simulate performance metrics
        for i in range(events // 2):
            metric_name = ["api_call", "db_query", "cache_hit"][i % 3]
            value = 50.0 + (i % 100)
            stats.add_performance_metric(metric_name, value)
        
        # Test data retrieval
        recent_events = stats.get_recent_member_events(50)
        memory_usage = stats.get_memory_usage()
        
        end_time = time.perf_counter()
        
        return {
            "members": members,
            "events_processed": events,
            "recent_events_count": len(recent_events),
            "estimated_memory_mb": memory_usage["estimated_memory_mb"],
            "duration_ms": (end_time - start_time) * 1000
        }
    
    async def _test_concurrent_operations(self, concurrent_tasks: int) -> Dict[str, Any]:
        """Test concurrent operations performance."""
        async def concurrent_task(task_id: int) -> Dict[str, Any]:
            # Simulate mixed workload
            stats = MemoryEfficientStats()
            
            for i in range(100):
                stats.add_member_event("join", task_id * 1000 + i, f"User{i}")
                stats.add_performance_metric(f"task_{task_id}_metric", i * 0.1)
            
            return {
                "task_id": task_id,
                "events_added": 100,
                "metrics_added": 100
            }
        
        start_time = time.perf_counter()
        
        # Run concurrent tasks
        tasks = [
            asyncio.create_task(concurrent_task(i))
            for i in range(concurrent_tasks)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = sum(1 for r in results if not isinstance(r, Exception))
        
        end_time = time.perf_counter()
        
        return {
            "concurrent_tasks": concurrent_tasks,
            "successful_tasks": successful,
            "duration_ms": (end_time - start_time) * 1000,
            "tasks_per_second": concurrent_tasks / (end_time - start_time)
        }
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information for benchmark context."""
        memory_stats = get_memory_usage()
        
        return {
            "python_version": sys.version,
            "platform": sys.platform,
            "memory_usage_mb": memory_stats.rss_mb,
            "memory_percent": memory_stats.percent,
            "available_memory_mb": memory_stats.available_mb
        }
    
    def _get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary from monitor."""
        return self.monitor.get_metrics_summary()


async def main():
    """Main benchmarking script."""
    parser = argparse.ArgumentParser(description="StatsBot Performance Benchmarker")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--output", "-o", help="Output file for results (JSON)")
    
    args = parser.parse_args()
    
    # Run benchmarks
    benchmarker = StatsBotBenchmarker(verbose=args.verbose)
    suite = await benchmarker.run_all_benchmarks()
    
    # Output results
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(asdict(suite), f, indent=2, default=str)
        
        print(f"📄 Results saved to {output_path}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Total Duration: {suite.total_duration_ms:.2f}ms")
    print(f"Tests Run: {suite.tests_run}")
    print(f"Passed: {suite.tests_passed}")
    print(f"Failed: {suite.tests_failed}")
    print(f"Success Rate: {(suite.tests_passed / suite.tests_run) * 100:.1f}%")
    
    if suite.tests_failed > 0:
        print("\n❌ FAILED TESTS:")
        for result in suite.results:
            if not result.success:
                print(f"  - {result.name}: {result.error_message}")
    
    print(f"\n🖥️  System: {suite.system_info['memory_usage_mb']:.1f}MB used")
    print("=" * 60)
    
    # Cleanup
    benchmarker.monitor.shutdown()
    
    return 0 if suite.tests_failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main()) 