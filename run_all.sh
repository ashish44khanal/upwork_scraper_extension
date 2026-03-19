#!/bin/bash

# Array to keep track of process IDs
pids=()

# Function to kill all started processes and shut down docker on exit
cleanup() {
    echo -e "\n🛑 Shutting down all services..."
    
    # Kill background PIDs (local scraper)
    for pid in "${pids[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
        fi
    done
    
    # Shut down Docker containers
    docker compose down
    
    wait
    echo "✅ All services stopped."
    exit
}

# Trap Ctrl+C (SIGINT) and SIGTERM
trap cleanup SIGINT SIGTERM

echo "🚀 Starting Hybrid Microservices Stack..."

# 1. Start Docker Compose (Infrastructure + Node Services)
echo "  -> Starting Docker Infrastructure (DB, Redis, Gateway, Extraction, Migrations)..."
docker compose up -d --remove-orphans

# 2. Start Scraper API (Local)
echo "  -> Starting Scraper API (Local)..."
(cd scraper_api && ./run_scraper.sh) &
pids+=($!)

echo -e "\n✨ All services are running! Press Ctrl+C to stop everything.\n"

# Keep the script running to catch signals
wait
