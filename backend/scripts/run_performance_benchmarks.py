#!/usr/bin/env python3
"""
Performance Benchmark Runner

This script runs comprehensive performance benchmarks for the Cosmos optimization.
It can be run independently or as part of the CI/CD pipeline.

Usage:
    python backend/scripts/run_performance_benchmarks.py [--output-file results.json] [--verbose]
"""

import asyncio
import json
import argparse
import sys
import os
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.test_performance_benchmarks import (
    ResponseTimeBenchmark,
    MemoryUsageBenchmark,
    RedisConnectionBenchmark,
    FileAccessBenchmark
)


class BenchmarkRunner:
    """Main benchmark runner that orchestrates all performance tests."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results = {}
        self.start_time = datetime.now()
    
    def log(self, message: str, level: str = "INFO"):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {level}: {message}")
    
    async def run_all_benchmarks(self) -> Dict[str, Any]:
        """Run all performance benchmarks and return consolidated results."""
        self.log("Starting performance benchmark suite")
        
        # Initialize results structure
        self.results = {
            'metadata': {
                'start_time': self.start_time.isoformat(),
                'version': '1.0.0',
                'environment': self._get_environment_info()
            },
            'benchmarks': {},
            'summary': {}
        }
        
        # Run Response Time Benchmark
        self.log("Running response time benchmark")
        try:
            response_benchmark = ResponseTimeBenchmark()
            response_results = await response_benchmark.benchmark_chat_response_time()
            response_validation = response_benchmark.validate_response_times(response_results)
            
            self.results['benchmarks']['response_time'] = {
                'results': response_results,
                'validation': response_validation,
                'target': response_benchmark.TARGET_RESPONSE_TIME,
                'passed': all(response_validation.values())
            }
            self.log(f"Response time benchmark completed: {'PASS' if all(response_validation.values()) else 'FAIL'}")
            
        except Exception as e:
            self.log(f"Response time benchmark failed: {e}", "ERROR")
            self.results['benchmarks']['response_time'] = {'error': str(e)}
        
        # Run Memory Usage Benchmark
        self.log("Running memory usage benchmark")
        try:
            memory_benchmark = MemoryUsageBenchmark()
            memory_results = memory_benchmark.benchmark_large_repository_memory()
            memory_validation = memory_benchmark.validate_memory_usage(memory_results)
            
            self.results['benchmarks']['memory_usage'] = {
                'results': memory_results,
                'validation': memory_validation,
                'target': memory_benchmark.TARGET_MEMORY_LIMIT,
                'passed': memory_validation
            }
            self.log(f"Memory usage benchmark completed: {'PASS' if memory_validation else 'FAIL'}")
            
        except Exception as e:
            self.log(f"Memory usage benchmark failed: {e}", "ERROR")
            self.results['benchmarks']['memory_usage'] = {'error': str(e)}
        
        # Run Redis Connection Benchmark
        self.log("Running Redis connection efficiency benchmark")
        try:
            redis_benchmark = RedisConnectionBenchmark()
            redis_results = redis_benchmark.benchmark_connection_efficiency()
            redis_validation = redis_benchmark.validate_connection_efficiency(redis_results)
            
            self.results['benchmarks']['redis_efficiency'] = {
                'results': redis_results,
                'validation': redis_validation,
                'target': redis_benchmark.TARGET_REUSE_RATE,
                'passed': redis_validation
            }
            self.log(f"Redis efficiency benchmark completed: {'PASS' if redis_validation else 'FAIL'}")
            
        except Exception as e:
            self.log(f"Redis efficiency benchmark failed: {e}", "ERROR")
            self.results['benchmarks']['redis_efficiency'] = {'error': str(e)}
        
        # Run File Access Benchmark
        self.log("Running file access time benchmark")
        try:
            file_benchmark = FileAccessBenchmark()
            file_results = file_benchmark.benchmark_file_access_times()
            file_validation = file_benchmark.validate_file_access_times(file_results)
            
            self.results['benchmarks']['file_access'] = {
                'results': file_results,
                'validation': file_validation,
                'target': file_benchmark.TARGET_ACCESS_TIME,
                'passed': all(file_validation.values())
            }
            self.log(f"File access benchmark completed: {'PASS' if all(file_validation.values()) else 'FAIL'}")
            
        except Exception as e:
            self.log(f"File access benchmark failed: {e}", "ERROR")
            self.results['benchmarks']['file_access'] = {'error': str(e)}
        
        # Generate summary
        self._generate_summary()
        
        self.log("All benchmarks completed")
        return self.results
    
    def _get_environment_info(self) -> Dict[str, Any]:
        """Get environment information for the benchmark run."""
        import platform
        import psutil
        
        return {
            'python_version': platform.python_version(),
            'platform': platform.platform(),
            'cpu_count': psutil.cpu_count(),
            'memory_total': psutil.virtual_memory().total / (1024**3),  # GB
            'hostname': platform.node()
        }
    
    def _generate_summary(self):
        """Generate a summary of all benchmark results."""
        benchmarks = self.results['benchmarks']
        
        # Count passed/failed benchmarks
        total_benchmarks = len(benchmarks)
        passed_benchmarks = sum(1 for b in benchmarks.values() 
                               if isinstance(b, dict) and b.get('passed', False))
        
        # Calculate overall performance score
        performance_score = (passed_benchmarks / total_benchmarks) * 100 if total_benchmarks > 0 else 0
        
        self.results['summary'] = {
            'total_benchmarks': total_benchmarks,
            'passed_benchmarks': passed_benchmarks,
            'failed_benchmarks': total_benchmarks - passed_benchmarks,
            'performance_score': performance_score,
            'overall_status': 'PASS' if passed_benchmarks == total_benchmarks else 'FAIL',
            'end_time': datetime.now().isoformat(),
            'total_duration': (datetime.now() - self.start_time).total_seconds()
        }
    
    def print_summary(self):
        """Print a human-readable summary of the benchmark results."""
        summary = self.results['summary']
        
        print("\n" + "="*60)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("="*60)
        
        print(f"Overall Status: {summary['overall_status']}")
        print(f"Performance Score: {summary['performance_score']:.1f}%")
        print(f"Total Duration: {summary['total_duration']:.2f} seconds")
        print()
        
        print("Benchmark Results:")
        print("-" * 30)
        
        for benchmark_name, benchmark_data in self.results['benchmarks'].items():
            if 'error' in benchmark_data:
                status = "ERROR"
                details = f"Error: {benchmark_data['error']}"
            else:
                status = "PASS" if benchmark_data.get('passed', False) else "FAIL"
                target = benchmark_data.get('target', 'N/A')
                details = f"Target: {target}"
            
            print(f"  {benchmark_name.replace('_', ' ').title()}: {status} ({details})")
        
        print()
        
        # Detailed results if verbose
        if self.verbose:
            print("Detailed Results:")
            print("-" * 30)
            for benchmark_name, benchmark_data in self.results['benchmarks'].items():
                if 'results' in benchmark_data:
                    print(f"\n{benchmark_name.replace('_', ' ').title()}:")
                    for key, value in benchmark_data['results'].items():
                        if isinstance(value, float):
                            print(f"  {key}: {value:.4f}")
                        else:
                            print(f"  {key}: {value}")
    
    def save_results(self, output_file: str):
        """Save benchmark results to a JSON file."""
        try:
            with open(output_file, 'w') as f:
                json.dump(self.results, f, indent=2, default=str)
            self.log(f"Results saved to {output_file}")
        except Exception as e:
            self.log(f"Failed to save results: {e}", "ERROR")


async def main():
    """Main entry point for the benchmark runner."""
    parser = argparse.ArgumentParser(description="Run Cosmos optimization performance benchmarks")
    parser.add_argument("--output-file", "-o", help="Output file for JSON results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--summary-only", "-s", action="store_true", help="Only print summary")
    
    args = parser.parse_args()
    
    # Create and run benchmark runner
    runner = BenchmarkRunner(verbose=args.verbose)
    
    try:
        results = await runner.run_all_benchmarks()
        
        # Print summary
        if not args.summary_only:
            runner.print_summary()
        
        # Save results if output file specified
        if args.output_file:
            runner.save_results(args.output_file)
        
        # Exit with appropriate code
        overall_status = results['summary']['overall_status']
        sys.exit(0 if overall_status == 'PASS' else 1)
        
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Benchmark runner failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())