import uvicorn
import logging
from src.main import app

# Configure logging for the entry point
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app_entry")

if __name__ == "__main__":
    logger.info("🚀 Starting Elite Upwork Scraper API from root entry point...")
    # Using the app object directly for compatibility with uv run
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
