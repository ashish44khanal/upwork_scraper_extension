from google import genai
import json
import os
import asyncio
from typing import Dict, Any
from datetime import datetime

class GeminiExtractor:
    """
    Gemini API-based HTML extractor using the new google.genai SDK.
    Extracts EXACT content from HTML without assumptions.
    """
    
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    def extract_from_html(self, html: str) -> Dict[str, Any]:
        """
        Extract job data from HTML using Gemini with STRICT instructions.
        """
        
        prompt = f"""You are a precise HTML data extractor. Your task is to extract job listing information from the provided HTML.

CRITICAL RULES:
1. Extract ONLY the exact text content from HTML elements - DO NOT add, modify, or assume anything
2. If a field is not found in the HTML, set it to null or empty array/object
3. DO NOT infer, summarize, or rephrase any content
4. Copy text EXACTLY as it appears in the HTML, character by character
5. For lists/arrays, extract each item exactly as shown
6. For numbers, extract as strings exactly as shown (e.g., "5" not 5)

EXTRACTION SCHEMA:
{{
  "job_title": "exact title text",
  "job_published_info": "exact posted time info like 'Posted 3 hours ago','Posted Yesterday'",
  "job_location_info": "exact location info text like is it worldwide open job or available for specific locations",
  "job_summary": "exact full description/summary text",
  "is_featured_job": "save value True if it is featured job False if not",
  "product_duration":"extract text from duration like 6+ months, 3 weeks",
  "hourly_commitment":"example: Less than 30 hrs/week",
  "project_type":"1. One-time project / 2. Ongoing project / 3. Complex project",
  "experience_level":"1. entry-level / 2. intermediate / 3. expert",
  "client_location":"Country name",
  "total_jobs_published_so_far":"String matching text",
  "hire_rate":"Percentage string",
  "no_of_current_opening_jobs_by_client":"String matching text",
  "total_spent":"String matching text",
  "avg_hourly_rate_paid":"String matching text",
  "total_paid_hours":"String matching text",
  "client_account_active_date":"String matching text",
  "no_of_proposal_received":"String matching text",
  "no_of_invites_sent":"String matching text",
  "talent_type":"String matching text",
  "list_of_skills_and_expertise_required_for_the_job": ["skill1", "skill2"],
  "client_rating_info": {{
    "total_reviews": "count",
    "avg_rating": "rating"
  }},
  "other_open_jobs_by_client": {{
    "no": "count",
    "list": [
      {{"job_title": "title", "link": "link"}}
    ]
  }},
  "client_recent_history": {{
    "total_numbers": "count",
    "jobs_in_progress": [
      {{ "name": "name", "job_link": "link", "start_date": "date", "no_of_hours": "hours", "per_hour_rate": "rate", "job_employee": "name" }}
    ]
  }}
}}

Return ONLY JSON.

{html}"""

        try:
            # Use the new SDK's generate_content
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0
                }
            )
            
            # Use parsed attribute if available or plain text
            data_text = response.text
            extracted_data = json.loads(data_text)
            
            # Map with safety (prevent 'list' has no attribute 'get')
            if isinstance(extracted_data, list) and len(extracted_data) > 0:
                extracted_data = extracted_data[0]
            elif not isinstance(extracted_data, dict):
                extracted_data = {}

            # Build standardized result
            fields = [
                "job_title", "job_published_info", "job_location_info", "job_summary",
                "is_featured_job", "product_duration", "hourly_commitment", "project_type",
                "experience_level", "client_location", "total_jobs_published_so_far",
                "hire_rate", "no_of_current_opening_jobs_by_client", "total_spent",
                "avg_hourly_rate_paid", "total_paid_hours", "client_account_active_date",
                "no_of_proposal_received", "no_of_invites_sent", "talent_type",
                "list_of_skills_and_expertise_required_for_the_job", "client_rating_info",
                "other_open_jobs_by_client", "client_recent_history"
            ]
            
            result = {f: extracted_data.get(f) for f in fields}
            result["scraped_at"] = datetime.now().isoformat()
            
            return result
            
        except Exception as e:
            print(f"Gemini (New SDK) extraction error: {e}")
            raise
    
    async def extract_from_html_async(self, html: str) -> Dict[str, Any]:
        """Async wrapper."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.extract_from_html, html)
