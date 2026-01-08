from bs4 import BeautifulSoup
from typing import Dict, Any, List

class DOMExtractor:
    """
    Local HTML extractor using BeautifulSoup (no API calls, 100% free).
    """
    
    def extract_from_html(self, html: str) -> Dict[str, Any]:
        """
        Extract structured data from HTML using BeautifulSoup.
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract title
        title = soup.title.string if soup.title else None
        
        # Extract meta description
        description = None
        meta_desc = soup.find('meta', attrs={'name': 'description'}) or \
                   soup.find('meta', attrs={'property': 'og:description'})
        if meta_desc:
            description = meta_desc.get('content')
        
        # Extract main headings
        main_headings = []
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            text = heading.get_text(strip=True)
            if text and len(text) > 3:  # Filter out empty or very short headings
                main_headings.append(text)
        
        # Extract key paragraphs as key points
        key_points = []
        for p in soup.find_all('p', limit=10):
            text = p.get_text(strip=True)
            if len(text) > 50:  # Only substantial paragraphs
                key_points.append(text[:200] + '...' if len(text) > 200 else text)
        
        # Extract important links
        links = []
        for a in soup.find_all('a', href=True, limit=15):
            link_text = a.get_text(strip=True)
            href = a.get('href', '')
            if link_text and href and link_text != href:  # Filter out icon/empty links
                links.append({
                    "text": link_text[:100],  # Limit link text length
                    "url": href
                })
        
        # Extract metadata
        metadata = {}
        
        # Try to find author
        author_meta = soup.find('meta', attrs={'name': 'author'})
        if author_meta:
            metadata['author'] = author_meta.get('content')
        
        # Try to find date
        date_meta = soup.find('meta', attrs={'property': 'article:published_time'}) or \
                   soup.find('time')
        if date_meta:
            metadata['date'] = date_meta.get('datetime') or date_meta.get('content') or date_meta.get_text(strip=True)
        
        # Job-specific extraction
        job_data = self._extract_job_fields(soup)
        
        return {
            "title": title,
            "description": description,
            "main_headings": main_headings[:10],
            "key_points": key_points[:5],
            "links": links[:10],
            "metadata": metadata,
            **job_data  # Merge job-specific fields
        }
    
    def _extract_job_fields(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract job listing specific fields."""
        job_data = {
            "job_title": None,
            "job_posted_timeline": None,
            "job_location": None,
            "job_summary": None,
            "job_info": {},
            "project_type": None,
            "skills_required": []
        }
        
        # Job Title - look for span with class containing "text-base"
        title_elem = soup.find('span', class_=lambda x: x and 'text-base' in x)
        if title_elem:
            job_data['job_title'] = title_elem.get_text(strip=True)
        
        # Job Posted Timeline
        posted_elem = soup.find('div', class_=lambda x: x and 'text-light-on-muted' in x and 'text-body-sm' in x)
        if posted_elem:
            posted_span = posted_elem.find('span')
            if posted_span:
                job_data['job_posted_timeline'] = f"Posted {posted_span.get_text(strip=True)}"
        
        # Job Location
        location_elem = soup.find('p', class_=lambda x: x and 'text-light-on-muted' in x and 'm-0' in x, attrs={'tabindex': '0'})
        if location_elem:
            job_data['job_location'] = location_elem.get_text(strip=True)
        
        # Job Summary
        summary_elem = soup.find('p', class_=lambda x: x and 'text-body-sm' in x and 'multiline-text' in x)
        if summary_elem:
            job_data['job_summary'] = summary_elem.get_text(strip=True)
        
        # Job Info (hours, duration, budget, experience)
        features_list = soup.find('ul', class_=lambda x: x and 'features' in x)
        if features_list:
            for li in features_list.find_all('li'):
                strong = li.find('strong')
                description = li.find('div', class_='description')
                if strong and description:
                    key = description.get_text(strip=True).lower()
                    value = strong.get_text(strip=True)
                    
                    if 'hourly' in key or 'hrs/week' in value.lower():
                        job_data['job_info']['hours'] = value
                    elif 'duration' in key or 'months' in value.lower():
                        job_data['job_info']['duration'] = value
                    elif 'experience' in key.lower():
                        job_data['job_info']['experience'] = value
                    elif '$' in value:
                        job_data['job_info']['budget'] = value
        
        # Project Type
        project_li = soup.find('li', string=lambda x: x and 'Project Type:' in x) if soup.find('li') else None
        if not project_li:
            # Try alternative approach
            for li in soup.find_all('li'):
                if li.find('strong', string=lambda x: x and 'Project Type:' in x):
                    span = li.find('span')
                    if span:
                        job_data['project_type'] = span.get_text(strip=True)
                    break
        
        # Skills Required
        skills_section = soup.find('section', class_=lambda x: x and 'air3-card-section' in x)
        if skills_section:
            skill_badges = skills_section.find_all('a', class_=lambda x: x and 'air3-badge' in x)
            for badge in skill_badges:
                skill_text = badge.get_text(strip=True)
                if skill_text and skill_text not in job_data['skills_required']:
                    job_data['skills_required'].append(skill_text)
        
        return job_data
