from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class DOMSubmission(BaseModel):
    dom_content: str

class UpworkSearchRequest(BaseModel):
    query: str
    num_jobs: Optional[int] = 5
    headless: Optional[bool] = False

class ExtractedData(BaseModel):
    # Core job fields - all optional
    job_title: Optional[str] = None
    job_summary: Optional[str] = None
    job_published_info: Optional[str] = None
    job_location_info: Optional[str] = None
    is_featured_job: Optional[bool] = None
    product_duration: Optional[str] = None
    hourly_commitment: Optional[str] = None
    project_type: Optional[str] = None
    experience_level: Optional[str] = None
    
    # Client information - all optional
    client_location: Optional[str] = None
    total_jobs_published_so_far: Optional[str] = None
    hire_rate: Optional[str] = None
    no_of_current_opening_jobs_by_client: Optional[str] = None
    total_spent: Optional[str] = None
    avg_hourly_rate_paid: Optional[str] = None
    total_paid_hours: Optional[str] = None
    client_account_active_date: Optional[str] = None
    
    # Activity
    no_of_proposal_received: Optional[str] = None
    no_of_invites_sent: Optional[str] = None
    talent_type: Optional[str] = None
    
    # Skills and Lists
    list_of_skills_and_expertise_required_for_the_job: Optional[List[str]] = None
    client_rating_info: Optional[Dict[str, str]] = None
    other_open_jobs_by_client: Optional[Dict[str, Any]] = None
    client_recent_history: Optional[Dict[str, Any]] = None
    scraped_at: Optional[str] = None
