from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class DOMSubmission(BaseModel):
    dom_content: str

class ExtractedData(BaseModel):
    # Core job fields - all optional
    job_title: Optional[str] = None
    job_summary: Optional[str] = None
    job_published_info: Optional[str] = None
    job_location_info: Optional[str] = None
    preferred_qualification_list: Optional[List[str]] = None
    activity_on_this_job_list: Optional[List[str]] = None
    list_of_skills_and_expertise_required_for_the_job: Optional[List[str]] = None
    
    # Client information - all optional
    client_rating_info: Optional[Dict[str, str]] = None
    other_open_jobs_by_client: Optional[Dict[str, Any]] = None
    client_recent_history: Optional[Dict[str, Any]] = None
