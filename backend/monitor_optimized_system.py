#!/usr/bin/env python3
"""
Monitoring Dashboard for Optimized Repository System

This script provides real-time monitoring of the optimized system performance,
showing metrics like response times, cache hit rates, and system health.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict, deque

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging to capture metrics
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class PerformanceMonitor:
    """Monitor performance metrics for the optimized repository system."""
    
    def __init__(self, window_size: int = 100):
        """
        Initialize performance monitor.
        
        Args:
            window_size: Number of recent operations to track
        """
        self.window_size = window_size
        self.metrics = defaultdict(lambda: deque(maxlen=window_size))
        self.start_time = time.time()
        
        # Counters
        self.operation_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.cache_hits = 0
        self.cache_misses = 0
    
    def record_operation(self, operation: str, duration: float, success: bool = True):
        """Record an operation metric."""
        self.metrics[operation].append({
            'duration': duration,
            'success': success,
            'timestamp': time.time()
        })
        
        self.operation_counts[operation] += 1
        if not success:
            self.error_counts[operation] += 1
    
    def record_cache_event(self, hit: bool):
        """Record a cache hit or miss."""
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
    
    def get_operation_stats(self, operation: str) -> Dict[str, Any]:
        """Get statistics for a specific operation."""
        if operation not in self.metrics:
            return {}
        
        durations = [m['duration'] for m in self.metrics[operation]]
        successes = [m['success'] for m in self.metrics[operation]]
        
        if not durations:
            return {}
        
        return {
            'count': len(durations),
            'avg_duration': sum(durations) / len(durations),
            'min_duration': min(durations),
            'max_duration': max(durations),
            'success_rate': sum(successes) / len(successes),
            'total_operations': self.operation_counts[operation],
            'total_errors': self.error_counts[operation]
        }
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return {'hit_rate': 0, 'total': 0}
        
        return {
            'hit_rate': self.cache_hits / total,
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'total': total
        }
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall system statistics."""
        uptime = time.time() - self.start_time
        
        return {
            'uptime_seconds': uptime,
            'uptime_formatted': str(timedelta(seconds=int(uptime))),
            'total_operations': sum(self.operation_counts.values()),
            'total_errors': sum(self.error_counts.values()),
            'operations_per_second': sum(self.operation_counts.values()) / uptime if uptime > 0 else 0
        }


def test_system_performance(monitor: PerformanceMonitor, test_repo: str = "https://github.com/microsoft/vscode"):
    """Test system performance and record metrics."""
    
    try:
        from services.optimized_repo_service import get_optimized_repo_service
        from middleware.optimized_repo_middleware import get_repo_middleware
        
        service = get_optimized_repo_service()
        middleware = get_repo_middleware()
        
        print(f"🧪 Testing performance with {test_repo}")
        
        # Test 1: Repository data access
        start_time = time.time()
        repo_data = service.get_repository_data(test_repo)
        duration = time.time() - start_time
        
        success = repo_data is not None
        monitor.record_operation('get_repository_data', duration * 1000, success)
        
        if success:
            monitor.record_cache_event(duration < 0.5)  # Consider < 500ms a cache hit
            print(f"   ✅ Repository data: {duration*1000:.2f}ms")
        else:
            print(f"   ❌ Repository data failed: {duration*1000:.2f}ms")
        
        # Test 2: File listing
        start_time = time.time()
        files = service.list_repository_files(test_repo)
        duration = time.time() - start_time
        
        success = len(files) > 0
        monitor.record_operation('list_files', duration * 1000, success)
        
        if success:
            print(f"   ✅ File listing ({len(files)} files): {duration*1000:.2f}ms")
        else:
            print(f"   ❌ File listing failed: {duration*1000:.2f}ms")
        
        # Test 3: File access
        test_files = ["README.md", "package.json", "index.html"]
        for file_path in test_files:
            start_time = time.time()
            content = service.get_file_content(test_repo, file_path)
            duration = time.time() - start_time
            
            success = content is not None
            monitor.record_operation('get_file_content', duration * 1000, success)
            
            if success:
                monitor.record_cache_event(duration < 0.1)  # Consider < 100ms a cache hit
                print(f"   ✅ {file_path}: {duration*1000:.2f}ms ({len(content)} chars)")
            else:
                print(f"   ❌ {file_path}: {duration*1000:.2f}ms (not found)")
        
        # Test 4: Middleware performance
        start_time = time.time()
        context = middleware.get_repository_context(test_repo, ["README.md"])
        duration = time.time() - start_time
        
        success = not context.get('error')
        monitor.record_operation('middleware_context', duration * 1000, success)
        
        if success:
            print(f"   ✅ Middleware context: {duration*1000:.2f}ms")
        else:
            print(f"   ❌ Middleware context failed: {duration*1000:.2f}ms")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Performance test failed: {e}")
        return False


def display_dashboard(monitor: PerformanceMonitor):
    """Display the monitoring dashboard."""
    
    # Clear screen (works on most terminals)
    os.system('clear' if os.name == 'posix' else 'cls')
    
    print("📊 Optimized Repository System - Performance Dashboard")
    print("=" * 70)
    print(f"🕐 Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Overall stats
    overall = monitor.get_overall_stats()
    print(f"\n🎯 Overall Statistics:")
    print(f"   Uptime: {overall['uptime_formatted']}")
    print(f"   Total Operations: {overall['total_operations']}")
    print(f"   Total Errors: {overall['total_errors']}")
    print(f"   Operations/sec: {overall['operations_per_second']:.2f}")
    
    # Cache stats
    cache_stats = monitor.get_cache_stats()
    if cache_stats['total'] > 0:
        print(f"\n💾 Cache Statistics:")
        print(f"   Hit Rate: {cache_stats['hit_rate']:.1%}")
        print(f"   Hits: {cache_stats['hits']}")
        print(f"   Misses: {cache_stats['misses']}")
        print(f"   Total: {cache_stats['total']}")
    
    # Operation stats
    operations = ['get_repository_data', 'list_files', 'get_file_content', 'middleware_context']
    
    print(f"\n⚡ Operation Performance:")
    print(f"{'Operation':<20} {'Count':<8} {'Avg (ms)':<10} {'Min (ms)':<10} {'Max (ms)':<10} {'Success':<8}")
    print("-" * 70)
    
    for operation in operations:
        stats = monitor.get_operation_stats(operation)
        if stats:
            print(f"{operation:<20} {stats['count']:<8} {stats['avg_duration']:<10.1f} "
                  f"{stats['min_duration']:<10.1f} {stats['max_duration']:<10.1f} "
                  f"{stats['success_rate']:<8.1%}")
    
    # System health
    try:
        from services.optimized_repo_service import get_optimized_repo_service
        service = get_optimized_repo_service()
        health = service.health_check()
        
        print(f"\n🏥 System Health:")
        print(f"   Overall: {'✅ Healthy' if health.get('overall_healthy') else '❌ Unhealthy'}")
        print(f"   Redis: {'✅ Connected' if health.get('redis_healthy') else '❌ Disconnected'}")
        print(f"   Storage: {'✅ Accessible' if health.get('storage_accessible') else '❌ Inaccessible'}")
        
    except Exception as e:
        print(f"\n🏥 System Health: ❌ Error checking health: {e}")
    
    print(f"\n📝 Performance Comparison:")
    print(f"   Old system estimate: ~6000ms per operation")
    
    # Calculate average performance
    avg_repo_data = monitor.get_operation_stats('get_repository_data').get('avg_duration', 0)
    avg_file_access = monitor.get_operation_stats('get_file_content').get('avg_duration', 0)
    
    if avg_repo_data > 0:
        improvement = ((6000 - avg_repo_data) / 6000) * 100
        print(f"   Repository data: {avg_repo_data:.1f}ms ({improvement:.1f}% improvement)")
    
    if avg_file_access > 0:
        improvement = ((6000 - avg_file_access) / 6000) * 100
        print(f"   File access: {avg_file_access:.1f}ms ({improvement:.1f}% improvement)")
    
    print(f"\n⌨️  Press Ctrl+C to exit")


def main():
    """Main monitoring function."""
    
    print("🚀 Starting Optimized Repository System Monitor")
    print("=" * 50)
    
    # Check if system is available
    try:
        from services.optimized_repo_service import get_optimized_repo_service
        service = get_optimized_repo_service()
        health = service.health_check()
        
        if not health.get('overall_healthy'):
            print("❌ System is not healthy. Please check configuration.")
            return
        
        print("✅ System is healthy. Starting monitoring...")
        
    except ImportError as e:
        print(f"❌ Could not import optimized system: {e}")
        return
    except Exception as e:
        print(f"❌ Error checking system health: {e}")
        return
    
    # Initialize monitor
    monitor = PerformanceMonitor()
    
    # Test repository (you can change this)
    test_repo = os.getenv('TEST_REPO_URL', 'https://github.com/microsoft/vscode')
    
    try:
        while True:
            # Run performance test
            test_system_performance(monitor, test_repo)
            
            # Display dashboard
            display_dashboard(monitor)
            
            # Wait before next update
            time.sleep(10)
            
    except KeyboardInterrupt:
        print(f"\n\n👋 Monitoring stopped.")
        
        # Print final summary
        overall = monitor.get_overall_stats()
        cache_stats = monitor.get_cache_stats()
        
        print(f"\n📊 Final Summary:")
        print(f"   Total runtime: {overall['uptime_formatted']}")
        print(f"   Total operations: {overall['total_operations']}")
        print(f"   Cache hit rate: {cache_stats.get('hit_rate', 0):.1%}")
        print(f"   Average ops/sec: {overall['operations_per_second']:.2f}")
        
        if overall['total_errors'] > 0:
            error_rate = overall['total_errors'] / overall['total_operations'] * 100
            print(f"   Error rate: {error_rate:.1f}%")
        else:
            print(f"   Error rate: 0.0%")


if __name__ == "__main__":
    main()