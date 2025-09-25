"""
Module loading performance monitor for web-optimized Cosmos
"""
import time
import sys
import psutil
import logging
from typing import Dict, List, Any
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class ModuleLoadMetrics:
    """Metrics for module loading performance"""
    module_name: str
    load_time: float
    memory_before: float
    memory_after: float
    memory_delta: float
    timestamp: datetime
    success: bool
    error_message: str = None

class ModulePerformanceMonitor:
    """
    Monitor and track module loading performance for optimization
    """
    
    def __init__(self):
        self.metrics: List[ModuleLoadMetrics] = []
        self.start_time = time.time()
        self.start_memory = self._get_memory_usage()
        
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024  # Convert to MB
        except:
            return 0.0
    
    def track_module_load(self, module_name: str):
        """
        Context manager to track module loading performance
        
        Usage:
            with monitor.track_module_load('cosmos.models'):
                import cosmos.models
        """
        return ModuleLoadTracker(self, module_name)
    
    def record_metrics(self, metrics: ModuleLoadMetrics):
        """Record module loading metrics"""
        self.metrics.append(metrics)
        
        if metrics.success:
            logger.debug(f"Module {metrics.module_name} loaded in {metrics.load_time:.3f}s, "
                        f"memory delta: {metrics.memory_delta:.2f}MB")
        else:
            logger.warning(f"Module {metrics.module_name} failed to load: {metrics.error_message}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        if not self.metrics:
            return {"status": "no_metrics"}
        
        successful_loads = [m for m in self.metrics if m.success]
        failed_loads = [m for m in self.metrics if not m.success]
        
        total_load_time = sum(m.load_time for m in successful_loads)
        total_memory_delta = sum(m.memory_delta for m in successful_loads)
        
        return {
            "total_modules": len(self.metrics),
            "successful_loads": len(successful_loads),
            "failed_loads": len(failed_loads),
            "total_load_time": total_load_time,
            "average_load_time": total_load_time / len(successful_loads) if successful_loads else 0,
            "total_memory_delta": total_memory_delta,
            "average_memory_delta": total_memory_delta / len(successful_loads) if successful_loads else 0,
            "slowest_modules": sorted(successful_loads, key=lambda x: x.load_time, reverse=True)[:5],
            "memory_heavy_modules": sorted(successful_loads, key=lambda x: x.memory_delta, reverse=True)[:5],
            "failed_modules": [m.module_name for m in failed_loads],
            "total_runtime": time.time() - self.start_time,
            "total_memory_usage": self._get_memory_usage() - self.start_memory
        }
    
    def get_optimization_recommendations(self) -> List[str]:
        """Get recommendations for module loading optimization"""
        recommendations = []
        summary = self.get_summary()
        
        if summary.get("failed_loads", 0) > 0:
            recommendations.append(f"Consider mocking {summary['failed_loads']} failed modules")
        
        if summary.get("average_load_time", 0) > 0.1:
            recommendations.append("Consider lazy loading for slow modules")
        
        if summary.get("total_memory_delta", 0) > 100:  # 100MB
            recommendations.append("High memory usage detected - consider selective imports")
        
        slowest = summary.get("slowest_modules", [])
        if slowest and slowest[0].load_time > 0.5:
            recommendations.append(f"Module {slowest[0].module_name} is slow to load ({slowest[0].load_time:.2f}s)")
        
        return recommendations
    
    def export_metrics(self) -> List[Dict[str, Any]]:
        """Export metrics as list of dictionaries"""
        return [asdict(metric) for metric in self.metrics]

class ModuleLoadTracker:
    """Context manager for tracking individual module loads"""
    
    def __init__(self, monitor: ModulePerformanceMonitor, module_name: str):
        self.monitor = monitor
        self.module_name = module_name
        self.start_time = None
        self.start_memory = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.start_memory = self.monitor._get_memory_usage()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.time()
        end_memory = self.monitor._get_memory_usage()
        
        metrics = ModuleLoadMetrics(
            module_name=self.module_name,
            load_time=end_time - self.start_time,
            memory_before=self.start_memory,
            memory_after=end_memory,
            memory_delta=end_memory - self.start_memory,
            timestamp=datetime.now(),
            success=exc_type is None,
            error_message=str(exc_val) if exc_val else None
        )
        
        self.monitor.record_metrics(metrics)

# Global monitor instance
performance_monitor = ModulePerformanceMonitor()

def get_performance_monitor() -> ModulePerformanceMonitor:
    """Get the global performance monitor instance"""
    return performance_monitor