#!/usr/bin/env python3
"""
Test script to fetch engine statistics from the VizAI Backend API.

This script calls the /admin/engine-stats endpoint to monitor
the external database engine cache.

Usage:
    python test_engine_stats.py

Requirements:
    - Backend server running (default: http://localhost:8000)
    - Valid authentication token
"""
import requests
import json
from typing import Optional

# Configuration
BASE_URL = "http://localhost:8000"  # Change if your backend runs on a different port
STATS_ENDPOINT = "/api/v1/backend/admin/engine-stats"


def get_auth_token() -> Optional[str]:
    """
    Get authentication token.

    You have two options:
    1. Set TOKEN environment variable: export TOKEN="your_jwt_token"
    2. Modify this function to return your token directly

    Returns:
        JWT token string or None
    """
    import os

    # Option 1: From environment variable
    token = os.environ.get("TOKEN")

    # Option 2: Hardcode for testing (NOT recommended for production)
    # token = "your_jwt_token_here"

    if not token:
        print("⚠️  No authentication token found!")
        print("   Set TOKEN environment variable: export TOKEN='your_token'")
        print("   Or modify get_auth_token() function in this script")

    return token


def fetch_engine_stats(base_url: str = BASE_URL, token: Optional[str] = None, stats_endpoint: str = STATS_ENDPOINT) -> dict:
    """
    Fetch engine statistics from the backend API.

    Args:
        base_url: Base URL of the backend API
        token: JWT authentication token

    Returns:
        Dictionary with engine statistics

    Raises:
        requests.RequestException: If the request fails
    """

    url = f"{base_url}{stats_endpoint}"

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    print(f"🔍 Fetching engine stats from: {url}")

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        return response.json()

    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            print(f"❌ Authentication failed: {e}")
            print("   Make sure you have a valid token")
        elif response.status_code == 403:
            print(f"❌ Forbidden: {e}")
            print("   Your token doesn't have permission to access this endpoint")
        else:
            print(f"❌ HTTP Error: {e}")
        raise

    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection failed: {e}")
        print(f"   Make sure the backend is running at {base_url}")
        raise

    except requests.exceptions.Timeout as e:
        print(f"❌ Request timed out: {e}")
        raise

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        raise


def display_stats(stats: dict):
    """
    Display engine statistics in a readable format.

    Args:
        stats: Statistics dictionary from the API
    """
    print("\n" + "="*60)
    print("🔧 EXTERNAL ENGINE CACHE STATISTICS")
    print("="*60)

    cached_engines = stats.get("cached_engines", 0)
    max_cache_size = stats.get("max_cache_size", 0)
    cache_utilization = stats.get("cache_utilization", "0.0%")
    connection_ids = stats.get("connection_ids", [])

    print(f"\n📊 Cache Overview:")
    print(f"   Cached Engines:    {cached_engines}")
    print(f"   Max Cache Size:    {max_cache_size}")
    print(f"   Cache Utilization: {cache_utilization}")

    if connection_ids:
        print(f"\n🔗 Cached Connection IDs ({len(connection_ids)}):")
        for idx, conn_id in enumerate(connection_ids, 1):
            print(f"   {idx}. {conn_id}")
    else:
        print(f"\n🔗 No connections currently cached")

    print("\n" + "="*60)

    # Health assessment
    utilization_pct = float(cache_utilization.rstrip('%'))
    if utilization_pct < 50:
        print("✅ Cache utilization is healthy")
    elif utilization_pct < 80:
        print("⚠️  Cache utilization is moderate")
    else:
        print("🔴 Cache utilization is high - consider increasing max_cache_size")

    print("="*60 + "\n")


def main():
    """Main function to run the test script."""
    print("🚀 VizAI Backend - Engine Stats Test\n")

    # Get authentication token
    token = get_auth_token()

    if not token:
        print("\n💡 Tip: You can still test without auth if the endpoint doesn't require it")
        response = input("Continue without token? (y/n): ")
        if response.lower() != 'y':
            return

    try:
        # Fetch stats
        stats = fetch_engine_stats(base_url= "http://170.187.237.181:8000", token=token)

        # Display stats
        display_stats(stats)

        health = fetch_engine_stats(base_url= "http://170.187.237.181:8000", token=token, stats_endpoint= "/api/v1/backend/health/pool-status")
        print("🩺 Pool Health Check:")
        print(health)

        # Also save to file
        output_file = "engine_stats_output.json"
        with open(output_file, 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"📁 Full response saved to: {output_file}\n")

    except Exception as e:
        print(f"\n❌ Failed to fetch engine stats: {e}\n")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
