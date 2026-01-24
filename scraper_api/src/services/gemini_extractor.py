import google.generativeai as genai
import json
import os
import asyncio
from typing import Dict, Any
from datetime import datetime

class GeminiExtractor:
    """
    Gemini API-based HTML extractor with strict prompting.
    Extracts EXACT content from HTML without assumptions.
    """
    
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        
        # Configure generation with strict JSON output
        generation_config = {
            "temperature": 0,  # No creativity - exact extraction only
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config
        )
    
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
  "project_type":"1. One-time project: A task with a clear start and finish (e.g., 'Design a logo').
                  2. Ongoing project: Continuous work with no set end date (e.g., Customer support).
                  3. Complex project: Larger initiatives that may require multiple milestones or different types of talent.",
  "experience_level":"extract the information about what kind of expertise the client is willing to pay for, 1. entry-level, 2. intermediate, 3. expert",
  "client_location":"extract the client location. For this information you can go to about the client section",
  "total_jobs_published_so_far":"extract the no of jobs posted by client. For this information you can go to about the client section",
  "hire_rate":"extract hire rate for eg: 45%",
  "no_of_current_opening_jobs_by_client":"extract open jobs. For example: 1 open job",
  "total_spent":"extract the total amount spent by client so far on the platform to hire people. for example $1.4K total spent",
  "avg_hourly_rate_paid":"extract avg hourly rate paid by client. For example $8.00 /hr",
  "total_paid_hours":" extract the total hours paid by client so far. For example 88 hours",
  "client_account_active_date":"extract the client membership data on the platform. For example Member since Apr 15, 2024",
  "no_of_proposal_received":"extract the numbers of proposals sent for this job so far under activity on this job section. For example 50+",
  "no_of_invites_sent":"extract the numbers of invites sent for this job so far under activity on this job section",
  "talent_type":"extract the text for Talent_Type under Preferred qualifications section. For example: independent",
  "list_of_skills_and_expertise_required_for_the_job": ["skill1", "skill2"],
  "client_rating_info": {{
    "total_reviews": "exact number",
    "avg_rating": "exact rating"
  }},
  "other_open_jobs_by_client": {{
    "no": "exact number of jobs",
    "list": [
      {{"job_title": "exact title", "link": "exact URL"}},
      {{"job_title": "exact title", "link": "exact URL"}}
    ]
  }},
  "client_recent_history": {{
    "total_numbers": "exact total number",
    "jobs_in_progress": [
      {{
        "name": "exact job name",
        "job_link": "exact job link",
        "start_date": "exact date",
        "no_of_hours": "exact hours",
        "per_hour_rate": "exact rate",
        "job_employee": "exact employee name"
      }}
    ]
  }}
}}

FEW-SHOT EXAMPLES:

Example 1 - Job Title:
HTML: <span class="text-base flex-1">Front end developer - AI tool user</span>
EXTRACT: {{"job_title": "Front end developer - AI tool user"}}
CORRECT ✓ - Exact match
WRONG ✗ - "Frontend Developer (AI Tools)" - Modified

Example 2 - Skills List:
HTML: <a class="air3-badge">HTML</a><a class="air3-badge">CSS</a><a class="air3-badge">JavaScript</a>
EXTRACT: {{"list_of_skills_and_expertise_required_for_the_job": ["HTML", "CSS", "JavaScript"]}}
CORRECT ✓ - Exact text from badges
WRONG ✗ - ["html", "css", "javascript"] - Changed case

Example 3 - Published Info:
HTML: <div>Posted <span>3 hours ago</span></div>
EXTRACT: {{"job_published_info": "Posted 3 hours ago"}}
CORRECT ✓ - Exact combined text
WRONG ✗ - "3 hours ago" - Missing "Posted"

Example 4 - Client Rating:
HTML: <div>4.5 out of 5</div><div>120 reviews</div>
EXTRACT: {{"client_rating_info": {{"avg_rating": "4.5 out of 5", "total_reviews": "120 reviews"}}}}
CORRECT ✓ - Exact text for both
WRONG ✗ - {{"avg_rating": "4.5", "total_reviews": "120"}} - Removed context

Now extract from this HTML (follow rules strictly):

{html}

Return ONLY the JSON with extracted data. NO additional text or explanations."""

        try:
            response = self.model.generate_content(prompt)
            extracted_data = json.loads(response.text)
            
            # Map to schema fields (all fields are optional, can be None)
            result = {
                "job_title": extracted_data.get("job_title"),
                "job_published_info": extracted_data.get("job_published_info"),
                "job_location_info": extracted_data.get("job_location_info"),
                "job_summary": extracted_data.get("job_summary"),
                "is_featured_job": extracted_data.get("is_featured_job"),
                "product_duration": extracted_data.get("product_duration"),
                "hourly_commitment": extracted_data.get("hourly_commitment"),
                "project_type": extracted_data.get("project_type"),
                "experience_level": extracted_data.get("experience_level"),
                "client_location": extracted_data.get("client_location"),
                "total_jobs_published_so_far": extracted_data.get("total_jobs_published_so_far"),
                "hire_rate": extracted_data.get("hire_rate"),
                "no_of_current_opening_jobs_by_client": extracted_data.get("no_of_current_opening_jobs_by_client"),
                "total_spent": extracted_data.get("total_spent"),
                "avg_hourly_rate_paid": extracted_data.get("avg_hourly_rate_paid"),
                "total_paid_hours": extracted_data.get("total_paid_hours"),
                "client_account_active_date": extracted_data.get("client_account_active_date"),
                "no_of_proposal_received": extracted_data.get("no_of_proposal_received"),
                "no_of_invites_sent": extracted_data.get("no_of_invites_sent"),
                "talent_type": extracted_data.get("talent_type"),
                "list_of_skills_and_expertise_required_for_the_job": extracted_data.get("list_of_skills_and_expertise_required_for_the_job"),
                "client_rating_info": extracted_data.get("client_rating_info"),
                "other_open_jobs_by_client": extracted_data.get("other_open_jobs_by_client"),
                "client_recent_history": extracted_data.get("client_recent_history"),
                "scraped_at": datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            print(f"Gemini extraction error: {e}")
            raise
    
    async def extract_from_html_async(self, html: str) -> Dict[str, Any]:
        """
        Async wrapper for extract_from_html to enable concurrent processing.
        Runs the synchronous Gemini API call in a thread pool.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.extract_from_html, html)
