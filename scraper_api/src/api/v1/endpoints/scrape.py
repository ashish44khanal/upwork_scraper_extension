from fastapi import APIRouter, HTTPException
from typing import List, Any
from fastapi.responses import Response
from src.schemas.extraction import DOMSubmission, ExtractedData, UpworkSearchRequest, UpworkScrapeRequest
from src.services.gemini_extractor import GeminiExtractor
from src.services.upwork_scraper import UpworkScraper
import json
import os
from datetime import datetime

router = APIRouter()
extractor = GeminiExtractor()

JOBS_FILE = "scraped_jobs.json"

@router.post("/extract", response_model=ExtractedData)
async def extract_dom(submission: DOMSubmission):
    """
    Extract structured data from HTML DOM using Gemini AI.
    Saves job data to JSON file.
    Accepts gzip-compressed base64-encoded DOM.
    """
    try:
        # Decompress the DOM content
        try:
            dom_content = decompress_dom(submission.dom_content)
            print(f"Received DOM (Compressed: {len(submission.dom_content)} bytes, Decompressed: {len(dom_content)} bytes)")
        except Exception as decompression_error:
            print(f"Decompression error: {decompression_error}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Decompression Failed",
                    "message": "Failed to decompress DOM content. The data may be corrupted.",
                    "type": "DECOMPRESSION_ERROR"
                }
            )
        
        # Extract data using Gemini
        try:
            extracted_data = extractor.extract_from_html(dom_content)
            print("\nExtraction completed successfully\n")
            print(f"Job Title: {extracted_data.get('job_title')}")
        except ValueError as api_error:
            # API key missing or invalid
            print(f"API configuration error: {api_error}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "API Configuration Error",
                    "message": str(api_error),
                    "type": "API_CONFIG_ERROR"
                }
            )
        except Exception as extraction_error:
            print(f"Extraction error: {extraction_error}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Extraction Failed",
                    "message": f"Failed to extract data from HTML: {str(extraction_error)}",
                    "type": "EXTRACTION_ERROR"
                }
            )
        
        # Save to JSON file
        try:
            save_to_json(extracted_data)
        except Exception as save_error:
            print(f"Save error: {save_error}")
            # Don't fail the request if save fails, just log it
            print("Warning: Failed to save to JSON file, but extraction succeeded")
        
        return ExtractedData(**extracted_data)
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch any unexpected errors
        print(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal Server Error",
                "message": "An unexpected error occurred during processing.",
                "type": "UNKNOWN_ERROR"
            }
        )

@router.post("/upwork", response_model=List[ExtractedData])
async def scrape_upwork(request: UpworkScrapeRequest):
    """
    Scrape jobs from Upwork at the given product URL.
    Logs in each run using UPWORK_USERNAME/UPWORK_PASSWORD from env.
    """
    try:
        scraper = UpworkScraper(headless=request.headless)
        results = await scraper.scrape_jobs(
            product_url=request.product_url,
            num_jobs=request.num_jobs,
        )
        await scraper.close()
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail="No jobs found or scraper was blocked by Cloudflare."
            )
            
        return [ExtractedData(**job) for job in results]
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Upwork critical API error: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Automation failure: {str(e)}"
        )

def decompress_dom(compressed_b64: str) -> str:
    """Decompress gzip-compressed base64-encoded DOM."""
    import gzip
    import base64
    
    try:
        # Decode base64
        compressed_data = base64.b64decode(compressed_b64)
        # Decompress gzip
        decompressed = gzip.decompress(compressed_data)
        # Decode to string
        return decompressed.decode('utf-8')
    except Exception as e:
        # If decompression fails, assume it's uncompressed (for backward compatibility)
        print(f"Decompression failed, treating as uncompressed: {e}")
        return compressed_b64

def save_to_json(data: dict):
    """Save extracted job data to JSON file."""
    # Add timestamp
    data['scraped_at'] = datetime.now().isoformat()
    
    # Read existing data
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE, 'r') as f:
            try:
                jobs = json.load(f)
            except json.JSONDecodeError:
                jobs = []
    else:
        jobs = []
    
    # Append new job
    jobs.append(data)
    
    # Write back to file
    with open(JOBS_FILE, 'w') as f:
        json.dump(jobs, f, indent=2)
    
    print(f"Saved job to {JOBS_FILE}. Total jobs: {len(jobs)}")

@router.get("/download")
async def download_scraped_jobs():
    """
    Download the scraped_jobs.json file.
    Returns the entire JSON file as a downloadable attachment.
    """
    try:
        # Use the same path as save_to_json (relative to working directory)
        if not os.path.exists(JOBS_FILE):
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "File Not Found",
                    "message": "No scraped jobs file found. Please scrape a job first.",
                    "type": "FILE_NOT_FOUND"
                }
            )
        
        # Read the entire file content
        with open(JOBS_FILE, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        # Verify it's valid JSON and contains all data
        try:
            jobs_data = json.loads(file_content)
            print(f"Downloading {len(jobs_data)} job(s) from scraped_jobs.json")
        except json.JSONDecodeError as e:
            print(f"Warning: File contains invalid JSON: {e}")
            # Still return the file content even if JSON is invalid
        
        # Return as downloadable JSON file with all content
        return Response(
            content=file_content,
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=scraped_jobs.json"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Download error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Download Failed",
                "message": f"Failed to download file: {str(e)}",
                "type": "DOWNLOAD_ERROR"
            }
        )
