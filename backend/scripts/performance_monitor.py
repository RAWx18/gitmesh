#!/usr/bin/env python3
"""
Continuous Performance Monitor

This script provides continuous monitoring of Cosmos optimization performance.
It can be used to track performance trends over time and alert on degradation.

Usage:
    python backend/scripts/performance_monitor.py [--interval 300] [--alert-threshold 0.8]
"""

import asyncio
import json
import time
import argparse
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
import logging

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.run_performance_benchmarks import BenchmarkRunner
from config.benchmark_config import validate_performance_result, get_benchmark_targets


class PerformanceMonitor:
    """Continuous performance monitoring system."""
    
    def __init__(self, interval: int = 300, alert_threshold: float = 0.8, 
                 history_file: str = "performance_history.json"):
        self.interval = interval  # seconds between checks
        self.alert_threshold = alert_threshold  # performance score threshold for alerts
        self.history_file = history_file
        self.history = []
        self.running = False
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('performance_monitor.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Load existing history
        self._load_history()
    
    def _load_history(self):
        """Load performance history from file."""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
                self.logger.info(f"Loaded {len(self.history)} historical records")
            else:
                self.history = []
                self.logger.info("No existing history file found, starting fresh")
        except Exception as e:
            self.logger.error(f"Failed to load history: {e}")
            self.history = []
    
    def _save_history(self):
        """Save performance history to file."""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to save history: {e}")
    
    async def run_single_check(self) -> Dict[str, Any]:
        """Run a single performance check."""
        self.logger.info("Running performance check...")
        
        try:
            runner = BenchmarkRunner(verbose=False)
            results = await runner.run_all_benchmarks()
            
            # Add to history
            self.history.append(results)
            
            # Keep only last 100 records to prevent unbounded growth
            if len(self.history) > 100:
                self.history = self.history[-100:]
            
            # Save updated history
            self._save_history()
            
            return results
            
        except Exception as e:
            self.logger.error(f"Performance check failed: {e}")
            return {'error': str(e), 'timestamp': datetime.now().isoformat()}
    
    def analyze_trends(self, lookback_hours: int = 24) -> Dict[str, Any]:
        """Analyze performance trends over the specified time period."""
        if not self.history:
            return {'error': 'No historical data available'}
        
        # Filter recent history
        cutoff_time = datetime.now() - timedelta(hours=lookback_hours)
        recent_history = []
        
        for record in self.history:
            try:
                record_time = datetime.fromisoformat(record['metadata']['start_time'])
                if record_time >= cutoff_time:
                    recent_history.append(record)
            except (KeyError, ValueError):
                continue
        
        if not recent_history:
            return {'error': f'No data available for last {lookback_hours} hours'}
        
        # Analyze trends
        trends = {}
        
        # Response time trend
        response_times = []
        memory_usage = []
        redis_efficiency = []
        file_access_times = []
        
        for record in recent_history:
            benchmarks = record.get('benchmarks', {})
            
            # Response time
            rt_data = benchmarks.get('response_time', {}).get('results', {})
            if rt_data:
                avg_time = sum(v for k, v in rt_data.items() if not k.endswith('_error')) / max(1, len([k for k in rt_data.keys() if not k.endswith('_error')]))
                response_times.append(avg_time)
            
            # Memory usage
            mem_data = benchmarks.get('memory_usage', {}).get('results', {})
            if mem_data and 'memory_used' in mem_data:
                memory_usage.append(mem_data['memory_used'])
            
            # Redis efficiency
            redis_data = benchmarks.get('redis_efficiency', {}).get('results', {})
            if redis_data and 'reuse_rate' in redis_data:
                redis_efficiency.append(redis_data['reuse_rate'])
            
            # File access times
            file_data = benchmarks.get('file_access', {}).get('results', {})
            if file_data and 'average_access_time' in file_data:
                file_access_times.append(file_data['average_access_time'])
        
        # Calculate trends
        trends['response_time'] = self._calculate_trend(response_times)
        trends['memory_usage'] = self._calculate_trend(memory_usage)
        trends['redis_efficiency'] = self._calculate_trend(redis_efficiency)
        trends['file_access_time'] = self._calculate_trend(file_access_times)
        
        # Overall health score
        health_scores = []
        for record in recent_history:
            summary = record.get('summary', {})
            if 'performance_score' in summary:
                health_scores.append(summary['performance_score'])
        
        trends['overall_health'] = self._calculate_trend(health_scores)
        
        return {
            'lookback_hours': lookback_hours,
            'records_analyzed': len(recent_history),
            'trends': trends,
            'current_values': {
                'response_time': response_times[-1] if response_times else None,
                'memory_usage': memory_usage[-1] if memory_usage else None,
                'redis_efficiency': redis_efficiency[-1] if redis_efficiency else None,
                'file_access_time': file_access_times[-1] if file_access_times else None,
                'overall_health': health_scores[-1] if health_scores else None
            }
        }
    
    def _calculate_trend(self, values: List[float]) -> Dict[str, Any]:
        """Calculate trend information for a series of values."""
        if len(values) < 2:
            return {'trend': 'insufficient_data', 'change': 0, 'values_count': len(values)}
        
        # Simple linear trend calculation
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]
        
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        
        change_percent = ((second_avg - first_avg) / first_avg) * 100 if first_avg != 0 else 0
        
        if abs(change_percent) < 5:
            trend = 'stable'
        elif change_percent > 0:
            trend = 'increasing'
        else:
            trend = 'decreasing'
        
        return {
            'trend': trend,
            'change_percent': change_percent,
            'first_half_avg': first_avg,
            'second_half_avg': second_avg,
            'values_count': len(values),
            'min_value': min(values),
            'max_value': max(values),
            'current_value': values[-1]
        }
    
    def check_alerts(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check if any alerts should be triggered based on results."""
        alerts = []
        
        # Check overall performance score
        summary = results.get('summary', {})
        performance_score = summary.get('performance_score', 0) / 100  # Convert to 0-1 scale
        
        if performance_score < self.alert_threshold:
            alerts.append({
                'type': 'performance_degradation',
                'severity': 'high' if performance_score < 0.5 else 'medium',
                'message': f'Performance score {performance_score:.2%} below threshold {self.alert_threshold:.2%}',
                'value': performance_score,
                'threshold': self.alert_threshold
            })
        
        # Check individual benchmarks
        benchmarks = results.get('benchmarks', {})
        
        for benchmark_name, benchmark_data in benchmarks.items():
            if 'error' in benchmark_data:
                alerts.append({
                    'type': 'benchmark_error',
                    'severity': 'high',
                    'message': f'{benchmark_name} benchmark failed: {benchmark_data["error"]}',
                    'benchmark': benchmark_name
                })
            elif not benchmark_data.get('passed', False):
                alerts.append({
                    'type': 'benchmark_failure',
                    'severity': 'medium',
                    'message': f'{benchmark_name} benchmark failed to meet targets',
                    'benchmark': benchmark_name,
                    'target': benchmark_data.get('target')
                })
        
        return alerts
    
    def send_alerts(self, alerts: List[Dict[str, Any]]):
        """Send alerts (currently just logs them, can be extended for email/Slack/etc.)."""
        for alert in alerts:
            severity = alert.get('severity', 'medium')
            message = alert.get('message', 'Unknown alert')
            
            if severity == 'high':
                self.logger.error(f"ALERT: {message}")
            else:
                self.logger.warning(f"ALERT: {message}")
    
    async def run_continuous_monitoring(self):
        """Run continuous performance monitoring."""
        self.running = True
        self.logger.info(f"Starting continuous monitoring (interval: {self.interval}s, threshold: {self.alert_threshold})")
        
        try:
            while self.running:
                # Run performance check
                results = await self.run_single_check()
                
                if 'error' not in results:
                    # Check for alerts
                    alerts = self.check_alerts(results)
                    
                    if alerts:
                        self.send_alerts(alerts)
                    
                    # Log summary
                    summary = results.get('summary', {})
                    performance_score = summary.get('performance_score', 0)
                    status = summary.get('overall_status', 'UNKNOWN')
                    
                    self.logger.info(f"Performance check completed: {status} (Score: {performance_score:.1f}%)")
                    
                    # Analyze trends every 10th check
                    if len(self.history) % 10 == 0:
                        trends = self.analyze_trends()
                        if 'error' not in trends:
                            self.logger.info("Trend analysis:")
                            for metric, trend_data in trends['trends'].items():
                                trend = trend_data.get('trend', 'unknown')
                                change = trend_data.get('change_percent', 0)
                                self.logger.info(f"  {metric}: {trend} ({change:+.1f}%)")
                
                else:
                    self.logger.error(f"Performance check failed: {results.get('error')}")
                
                # Wait for next interval
                await asyncio.sleep(self.interval)
                
        except KeyboardInterrupt:
            self.logger.info("Monitoring stopped by user")
        except Exception as e:
            self.logger.error(f"Monitoring failed: {e}")
        finally:
            self.running = False
    
    def stop(self):
        """Stop continuous monitoring."""
        self.running = False
        self.logger.info("Stopping performance monitoring...")


async def main():
    """Main entry point for the performance monitor."""
    parser = argparse.ArgumentParser(description="Continuous performance monitoring for Cosmos optimization")
    parser.add_argument("--interval", "-i", type=int, default=300, help="Check interval in seconds (default: 300)")
    parser.add_argument("--alert-threshold", "-t", type=float, default=0.8, help="Performance score threshold for alerts (default: 0.8)")
    parser.add_argument("--history-file", "-f", default="performance_history.json", help="History file path")
    parser.add_argument("--analyze-only", "-a", action="store_true", help="Only analyze trends, don't run continuous monitoring")
    parser.add_argument("--lookback-hours", "-l", type=int, default=24, help="Hours to look back for trend analysis")
    
    args = parser.parse_args()
    
    monitor = PerformanceMonitor(
        interval=args.interval,
        alert_threshold=args.alert_threshold,
        history_file=args.history_file
    )
    
    if args.analyze_only:
        # Just analyze trends and exit
        trends = monitor.analyze_trends(args.lookback_hours)
        print(json.dumps(trends, indent=2, default=str))
        return
    
    try:
        await monitor.run_continuous_monitoring()
    except KeyboardInterrupt:
        monitor.stop()
        print("\nMonitoring stopped")


if __name__ == "__main__":
    asyncio.run(main())