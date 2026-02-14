import asyncio
import json
import logging
import os
import redis
import redis.asyncio as aioredis
import base64
from datetime import datetime
from src.core.config import settings
from src.services.upwork_scraper import UpworkScraper

logger = logging.getLogger(__name__)

class RedisStreamReader:
    def __init__(self):
        self.redis_client = None
        # Manager for singleton browser lifecycle
        self.manager_scraper = UpworkScraper(headless=False)
        self.semaphore = asyncio.Semaphore(8) # Limit to 8 concurrent tabs
        self.stream_name = settings.REDIS_STREAM_NAME
        self.group_name = settings.REDIS_GROUP_NAME
        self.consumer_name = settings.REDIS_CONSUMER_NAME

    async def connect(self):
        try:
            self.redis_client = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=True
            )
            logger.info(f"Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            
            # Ensure scraper group exists
            try:
                await self.redis_client.xgroup_create(self.stream_name, self.group_name, id="0", mkstream=True)
                logger.info(f"Created consumer group {self.group_name} on stream {self.stream_name}")
            except redis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    logger.info(f"Consumer group {self.group_name} already exists")
                else:
                    raise e
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise e

    async def _handle_card_data(self, card_index, page_num, raw_html, filtered_html, url, stream_id, extraction_mode):
        """
        Callback from scraper for each card:
        1. Saves Filtered HTML.
        2. Publishes event to extraction stream.
        """
        try:
            filename_base = f"{stream_id}_p{page_num}_c{card_index}"
            os.makedirs(settings.STORAGE_DIR, exist_ok=True)
            
            html_path = os.path.abspath(os.path.join(settings.STORAGE_DIR, f"{filename_base}.html"))
            
            # Save Filtered HTML
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(filtered_html)
            
            # Publish event
            event_data = {
                "original_stream_id": stream_id,
                "card_index": str(card_index),
                "page_num": str(page_num),
                "html_path": html_path,
                "url": url,
                "extraction_mode": extraction_mode,
                "status": "card_captured",
                "timestamp": datetime.now().isoformat()
            }
            
            new_msg_id = await self.redis_client.xadd(
                settings.EXTRACTION_STREAM_NAME, 
                event_data
            )
            logger.info(f"Published card event {new_msg_id} for {stream_id} (Card {card_index})")
            
        except Exception as e:
            logger.error(f"Error in card callback for {stream_id} card {card_index}: {e}")

    async def process_message(self, message_id, data):
        """
        Process a single message from the Redis stream with Semaphore isolation.
        Each message runs in its own tab.
        """
        async with self.semaphore:
            logger.info(f"🚀 Starting background process for {message_id} (active: {8 - self.semaphore._value})")
            
            page_url = data.get("page_url")
            if not page_url:
                logger.warning(f"No page_url found in message {message_id}")
                return

            extraction_mode = data.get("extraction_mode", "manual")
            pages_to_scrape = int(data.get("pages", settings.DEFAULT_SCRAPE_PAGES))

            # Isolated scraper for this specific task
            task_scraper = UpworkScraper(headless=False)
            
            try:
                async def card_callback(**kwargs):
                    await self._handle_card_data(
                        stream_id=message_id, 
                        extraction_mode=extraction_mode, 
                        **kwargs
                    )

                await task_scraper.scrape_jobs(
                    product_url=page_url,
                    no_of_pages_to_scrape=pages_to_scrape,
                    on_card_data_async=card_callback
                )
                
                # Acknowledge the original message
                await self.redis_client.xack(self.stream_name, self.group_name, message_id)
                logger.info(f"✅ Finished and Acknowledged message {message_id}")
                
            except Exception as e:
                logger.error(f"❌ Error processing search request {message_id}: {e}")
            finally:
                # Close only this specific tab
                await task_scraper.close()

    async def run(self):
        await self.connect()
        logger.info(f"Starting Redis stream reader on stream: {self.stream_name}")
        
        # Warmup: Ensure singleton session is ready before processing streams
        logger.info("🛠️  Preparing Elite Scraper environment...")
        await self.manager_scraper.verify_session()
        
        try:
            while True:
                try:
                    messages = await self.redis_client.xreadgroup(
                        groupname=self.group_name,
                        consumername=self.consumer_name,
                        streams={self.stream_name: ">"},
                        count=1,
                        block=5000
                    )
                    
                    if not messages:
                        continue
                        
                    for stream, msgs in messages:
                        for message_id, data in msgs:
                            # Dispatch task asynchronously
                            asyncio.create_task(self.process_message(message_id, data))
                except Exception as e:
                    logger.error(f"Error reading from stream: {e}")
                    await asyncio.sleep(5)
                    
        finally:
            if self.redis_client:
                await self.redis_client.close()
            # Final browser shutdown
            await UpworkScraper.shutdown()

async def main():
    logging.basicConfig(level=logging.INFO)
    reader = RedisStreamReader()
    await reader.run()

if __name__ == "__main__":
    asyncio.run(main())
