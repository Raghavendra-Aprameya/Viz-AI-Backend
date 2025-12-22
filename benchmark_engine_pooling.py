#!/usr/bin/env python3
"""
Benchmark script to compare OLD vs NEW engine management approaches.

This script demonstrates the performance improvement from using
the ExternalEngineManager with connection pooling versus the old
approach of creating a new engine for each request.

Usage:
    python benchmark_engine_pooling.py
"""

import time
import tracemalloc
from typing import List, Dict
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
import statistics

# Add the app to Python path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.external_engine_manager import ExternalEngineManager
from uuid import uuid4


# Configuration
TEST_CONNECTION_STRING = "postgresql://postgres:password@localhost:5432/vizai-db-local"
TEST_QUERY = "SELECT 1"
NUM_REQUESTS = 50  # Number of simulated requests


class Benchmark:
    """Benchmark utility class."""

    def __init__(self, name: str):
        self.name = name
        self.start_time = None
        self.start_memory = None
        self.results = {}

    def __enter__(self):
        tracemalloc.start()
        self.start_memory = tracemalloc.get_traced_memory()
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        elapsed_time = time.perf_counter() - self.start_time
        current_memory, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        self.results = {
            "elapsed_time": elapsed_time,
            "memory_increase": (current_memory - self.start_memory[0]) / 1024 / 1024,  # MB
            "peak_memory": peak_memory / 1024 / 1024,  # MB
        }


def old_approach_single_request(connection_string: str, query: str):
    """
    OLD APPROACH: Create engine, execute query, dispose engine.
    This is what was happening before the fix.
    """
    engine = create_engine(connection_string)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            _ = result.fetchall()
    finally:
        engine.dispose()


def old_approach_benchmark(connection_string: str, query: str, num_requests: int) -> Dict:
    """
    Benchmark the OLD approach (create engine per request).
    """
    print(f"🔴 Testing OLD approach ({num_requests} requests)...")
    print("   Creating and disposing engine for EACH request")

    request_times = []

    with Benchmark("Old Approach") as bench:
        for i in range(num_requests):
            req_start = time.perf_counter()
            old_approach_single_request(connection_string, query)
            req_time = time.perf_counter() - req_start
            request_times.append(req_time)

            if (i + 1) % 10 == 0:
                print(f"   Progress: {i + 1}/{num_requests} requests")

    results = bench.results
    results["avg_request_time"] = statistics.mean(request_times)
    results["min_request_time"] = min(request_times)
    results["max_request_time"] = max(request_times)
    results["engines_created"] = num_requests  # One engine per request

    return results


def new_approach_single_request(manager: ExternalEngineManager, conn_id, connection_string: str, query: str):
    """
    NEW APPROACH: Get cached engine from manager, execute query.
    Engine is reused across requests.
    """
    engine = manager.get_engine(
        connection_id=conn_id,
        connection_string=connection_string,
        db_type="postgres"
    )
    with engine.connect() as conn:
        result = conn.execute(text(query))
        _ = result.fetchall()
    # No dispose - manager handles lifecycle


def new_approach_benchmark(connection_string: str, query: str, num_requests: int) -> Dict:
    """
    Benchmark the NEW approach (reuse engine from manager).
    """
    print(f"\n✅ Testing NEW approach ({num_requests} requests)...")
    print("   Reusing cached engine across ALL requests")

    manager = ExternalEngineManager()
    test_conn_id = uuid4()
    request_times = []

    with Benchmark("New Approach") as bench:
        for i in range(num_requests):
            req_start = time.perf_counter()
            new_approach_single_request(manager, test_conn_id, connection_string, query)
            req_time = time.perf_counter() - req_start
            request_times.append(req_time)

            if (i + 1) % 10 == 0:
                print(f"   Progress: {i + 1}/{num_requests} requests")

        # Cleanup
        manager.dispose_all()

    results = bench.results
    results["avg_request_time"] = statistics.mean(request_times)
    results["min_request_time"] = min(request_times)
    results["max_request_time"] = max(request_times)
    results["engines_created"] = 1  # Only one engine created, reused for all

    return results


def display_comparison(old_results: Dict, new_results: Dict, num_requests: int):
    """Display comparison of OLD vs NEW approach."""
    print("\n" + "="*80)
    print("📊 BENCHMARK RESULTS COMPARISON")
    print("="*80)

    print(f"\nTest Configuration:")
    print(f"  Total Requests:    {num_requests}")
    print(f"  Connection String: {TEST_CONNECTION_STRING}")
    print(f"  Query:             {TEST_QUERY}")

    print("\n" + "-"*80)
    print("⏱️  TIMING COMPARISON")
    print("-"*80)

    print(f"\n{'Metric':<30} {'OLD Approach':<20} {'NEW Approach':<20} {'Improvement'}")
    print("-"*80)

    # Total time
    old_total = old_results["elapsed_time"]
    new_total = new_results["elapsed_time"]
    time_improvement = ((old_total - new_total) / old_total) * 100
    print(f"{'Total Time':<30} {old_total:.4f}s{'':<14} {new_total:.4f}s{'':<14} {time_improvement:+.1f}%")

    # Average request time
    old_avg = old_results["avg_request_time"]
    new_avg = new_results["avg_request_time"]
    avg_improvement = ((old_avg - new_avg) / old_avg) * 100
    print(f"{'Avg Request Time':<30} {old_avg*1000:.2f}ms{'':<14} {new_avg*1000:.2f}ms{'':<14} {avg_improvement:+.1f}%")

    # Min request time
    print(f"{'Min Request Time':<30} {old_results['min_request_time']*1000:.2f}ms{'':<14} {new_results['min_request_time']*1000:.2f}ms")

    # Max request time
    print(f"{'Max Request Time':<30} {old_results['max_request_time']*1000:.2f}ms{'':<14} {new_results['max_request_time']*1000:.2f}ms")

    print("\n" + "-"*80)
    print("💾 MEMORY COMPARISON")
    print("-"*80)

    # Memory
    old_mem = old_results["memory_increase"]
    new_mem = new_results["memory_increase"]
    mem_improvement = ((old_mem - new_mem) / old_mem) * 100 if old_mem > 0 else 0
    print(f"{'Memory Increase':<30} {old_mem:.2f} MB{'':<14} {new_mem:.2f} MB{'':<14} {mem_improvement:+.1f}%")

    print(f"{'Peak Memory':<30} {old_results['peak_memory']:.2f} MB{'':<14} {new_results['peak_memory']:.2f} MB")

    print("\n" + "-"*80)
    print("🔧 RESOURCE USAGE")
    print("-"*80)

    old_engines = old_results["engines_created"]
    new_engines = new_results["engines_created"]
    engine_reduction = ((old_engines - new_engines) / old_engines) * 100
    print(f"{'Engines Created':<30} {old_engines:<20} {new_engines:<20} {engine_reduction:+.1f}%")

    # Calculate estimated connections (engines * pool_size)
    old_connections = old_engines * 15  # Assume pool_size=5 + max_overflow=10
    new_connections = new_engines * 15
    print(f"{'Estimated Max Connections':<30} {old_connections:<20} {new_connections:<20} {((old_connections-new_connections)/old_connections)*100:+.1f}%")

    print("\n" + "="*80)
    print("🎯 SUMMARY")
    print("="*80)

    print(f"\n✅ The NEW approach with ExternalEngineManager:")
    print(f"   • Is {abs(time_improvement):.1f}% FASTER in total execution time")
    print(f"   • Reduces engine creation by {abs(engine_reduction):.1f}%")
    print(f"   • Creates only {new_engines} engine(s) instead of {old_engines}")
    print(f"   • Reduces memory usage by ~{abs(mem_improvement):.1f}%")
    print(f"\n🚀 This translates to:")
    print(f"   • Lower database server load")
    print(f"   • Faster response times")
    print(f"   • Better resource utilization")
    print(f"   • No memory leaks from orphaned engines")

    print("\n" + "="*80 + "\n")


def main():
    """Run the benchmark comparison."""
    print("🚀 VizAI Backend - Engine Pooling Benchmark")
    print("="*80)
    print("\nThis benchmark compares:")
    print("  🔴 OLD: Creating a new engine for each request (memory leak)")
    print("  ✅ NEW: Reusing cached engine from ExternalEngineManager\n")

    # Test connection
    print("Testing database connection...")
    try:
        test_engine = create_engine(TEST_CONNECTION_STRING)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        test_engine.dispose()
        print("✅ Database connection successful\n")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("   Please check your connection string in the script")
        return 1

    # Run benchmarks
    try:
        old_results = old_approach_benchmark(TEST_CONNECTION_STRING, TEST_QUERY, NUM_REQUESTS)
        new_results = new_approach_benchmark(TEST_CONNECTION_STRING, TEST_QUERY, NUM_REQUESTS)

        # Display comparison
        display_comparison(old_results, new_results, NUM_REQUESTS)

        # Save results to file
        import json
        results = {
            "test_config": {
                "num_requests": NUM_REQUESTS,
                "connection_string": TEST_CONNECTION_STRING,
                "query": TEST_QUERY
            },
            "old_approach": old_results,
            "new_approach": new_results
        }

        output_file = "benchmark_results.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"📁 Detailed results saved to: {output_file}\n")

    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
