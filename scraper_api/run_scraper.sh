#!/bin/bash

# Configuration for host-local run
export POSTGRES_HOST=localhost
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=postgres
export POSTGRES_DB=upwork_db

# Redis is running in Docker and exposed on 6379
export REDIS_HOST=localhost
export REDIS_PORT=6379

echo "🚀 Starting Scraper API on host..."
uv run src/main.py
