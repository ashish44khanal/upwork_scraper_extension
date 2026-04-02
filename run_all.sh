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

# Parse arguments
BUILD_FLAG=""
RUN_MIGRATION=false
for arg in "$@"; do
    if [ "$arg" == "--build" ]; then
        BUILD_FLAG="--build"
    fi
    if [ "$arg" == "--runMigration" ]; then
        RUN_MIGRATION=true
    fi
done

echo "🚀 Starting Hybrid Microservices Stack..."

# 1. Start Docker Compose (Infrastructure + Node Services)
echo "  -> Starting Docker Infrastructure (DB, Redis, Gateway, Extraction)..."
docker compose up -d $BUILD_FLAG --remove-orphans

# 2. Run Database Migrations if requested
if [ "$RUN_MIGRATION" = true ]; then
    echo "  -> Waiting for Database to be healthy..."
    # Wait for the DB container to be healthy (using the healthcheck defined in docker-compose.yml)
    # We use 'docker compose ps' to find the container name dynamically
    DB_CONTAINER=$(docker compose ps -q db)
    until [ "$(docker inspect -f '{{.State.Health.Status}}' $DB_CONTAINER)" == "healthy" ]; do
        echo "     (Waiting...)"
        sleep 2
    done
    
    echo "  -> Running Database Migrations (Inside Container)..."
    # We run the migration inside the container to avoid needing node_modules on the host
    docker compose exec extraction_service npm run migration:run:prod
fi

# 3. Start Scraper API (Local)
echo "  -> Starting Scraper API (Local)..."
(cd scraper_api && ./run_scraper.sh) &
pids+=($!)

echo -e "\n✨ All services are running! Press Ctrl+C to stop everything.\n"

# Keep the script running to catch signals
wait
