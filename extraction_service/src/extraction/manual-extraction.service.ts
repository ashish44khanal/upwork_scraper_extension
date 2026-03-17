import { Injectable, Logger } from '@nestjs/common';
import * as cheerio from 'cheerio';
import { ExtractedJobDto } from '../dto/extracted-job.dto';

@Injectable()
export class ManualExtractionService {
  private readonly logger = new Logger(ManualExtractionService.name);

  /**
   * Extract structured data from HTML using Cheerio.
   * EXACT parity with Python DOMExtractor logic and schema.
   */
  async extractData(html: string): Promise<ExtractedJobDto> {
    const $full = cheerio.load(html);
    const data: ExtractedJobDto = {};

    // Filter for job details slider
    const sliderSelector = 'div.air3-slider-content[slidername="job-details-slider"], [data-test="UpCSliderBody"]';
    const slider = $full(sliderSelector).first();
    
    let $context = $full;
    if (slider.length > 0) {
      this.logger.log('Found job details slider, narrowing extraction context.');
      $context = cheerio.load(slider.html() || '');
    } else {
      this.logger.warn('Job details slider not found, using full document.');
    }

    // Job-specific extraction from context
    const jobData = this._extractJobFields($context, $full);
    Object.assign(data, jobData);
    
    data.scraped_at = new Date().toISOString();

    this.logger.log(`Manually extracted data (Python Parity) for: ${data.job_title || 'Unknown'}`);
    return data;
  }

  private _extractJobFields($: cheerio.CheerioAPI, $full: cheerio.CheerioAPI): Partial<ExtractedJobDto> {
    const jobData: Partial<ExtractedJobDto> = {
      job_title: undefined,
      job_published_info: undefined,
      job_location_info: undefined,
      job_summary: undefined,
      is_featured_job: false,
      product_duration: undefined,
      hourly_commitment: undefined,
      project_type: undefined,
      experience_level: undefined,
      client_location: undefined,
      total_jobs_published_so_far: undefined,
      hire_rate: undefined,
      no_of_current_opening_jobs_by_client: undefined,
      total_spent: undefined,
      avg_hourly_rate_paid: undefined,
      total_paid_hours: undefined,
      client_account_active_date: undefined,
      no_of_proposal_received: undefined,
      no_of_invites_sent: undefined,
      talent_type: undefined,
      list_of_skills_and_expertise_required_for_the_job: [],
      client_rating_info: {},
      other_open_jobs_by_client: { list: [] },
      client_recent_history: { jobs_in_progress: [] },
    };

    // 1. Job Title
    jobData.job_title = $('h4 .text-base.flex-1').first().text().trim() ||
                        $('[data-qa="job-title"]').first().text().trim() ||
                        $('.job-details-header h1').first().text().trim() ||
                        $('h1').first().text().trim() || 
                        $('h4').first().text().trim() ||
                        undefined;

    // 2. Published & Location Info
    const postedElem = $('[data-test="PostedOn"], [data-qa="posted-on"]');
    jobData.job_published_info = postedElem.first().text().trim().replace(/Posted\n/g, 'Posted ').replace(/\s+/g, ' ') || undefined;
    
    jobData.job_location_info = $('[data-test="LocationLabel"] p').first().text().trim() ||
                                $('[data-qa="client-location"]').first().text().trim() ||
                                undefined;

    // 3. Job Summary
    jobData.job_summary = $('p.multiline-text').first().text().trim() ||
                          $('.job-description').first().text().trim() ||
                          $('[data-qa="job-description"]').first().text().trim() ||
                          undefined;

    // 4. Featured Job
    jobData.is_featured_job = $('.featured-job-badge, [data-qa="featured-job"]').length > 0;

    // 5. Features (Duration, Hourly, Exp)
    $('[data-test="Features"] li').each((_, li) => {
      const val = $(li).find('strong').text().trim();
      const key = $(li).find('.description').text().trim().toLowerCase();
      
      if (key.includes('hourly') || val.toLowerCase().includes('hrs/week')) {
        jobData.hourly_commitment = val;
      } else if (key.includes('duration') || val.toLowerCase().includes('month') || val.toLowerCase().includes('week')) {
        jobData.product_duration = val;
      } else if (key.includes('experience')) {
        jobData.experience_level = val;
      }
    });

    // 6. Project Type
    $('[data-test="Segmentations"] li').each((_, el) => {
      const text = $(el).text().trim();
      if (text.includes('Project Type:')) {
        jobData.project_type = text.split('Project Type:')[1]?.trim();
        return false;
      }
    });

    // 7. Client Information
    jobData.client_location = $('[data-qa="client-location"] strong').text().trim() || jobData.job_location_info;
    jobData.total_jobs_published_so_far = $('[data-qa="client-job-posting-stats"]').text().replace(/\s+/g, ' ').trim() || undefined;
    jobData.hire_rate = $('[data-qa="client-job-posting-stats"]').text().match(/\d+%/)?.[0] || undefined;
    
    const spentText = $('[data-qa="client-spend"]').text().trim();
    jobData.total_spent = spentText ? (spentText + ' total spent') : undefined;
    
    jobData.avg_hourly_rate_paid = $('[data-qa="client-hourly-rate"]').text().trim() || undefined;
    jobData.total_paid_hours = $('[data-qa="client-hours"]').text().trim() || undefined;
    jobData.client_account_active_date = $('[data-qa="client-contract-date"]').text().trim() || undefined;
    jobData.no_of_proposal_received = $('[data-test="Proposals"] .value').text().trim() || undefined;
    jobData.no_of_invites_sent = $('[data-test="InvitesSent"] .value').text().trim() || '0';

    // 8. Skills Required
    const skills: string[] = [];
    $('[data-test="Skill"], .air3-badge, [data-qa="skill"]').each((_, el) => {
      const skillText = $(el).text().trim();
      if (skillText && !skills.includes(skillText)) {
        skills.push(skillText);
      }
    });
    jobData.list_of_skills_and_expertise_required_for_the_job = skills;

    // 9. Client Rating
    const ratingElem = $('[data-qa="client-rating"]');
    if (ratingElem.length > 0) {
      jobData.client_rating_info = {
        avg_rating: ratingElem.find('.air3-rating-star strong').text().trim() || undefined,
        total_reviews: ratingElem.text().match(/\d+\s+review/)?.[0] || undefined,
      };
    }

    // 10. Other Open Jobs
    const otherJobs: any[] = [];
    $('[data-qa="client-other-jobs"] li, .other-jobs li').each((_, el) => {
      const title = $(el).find('a').text().trim();
      const link = $(el).find('a').attr('href');
      if (title && link) {
        otherJobs.push({ job_title: title, link });
      }
    });
    jobData.other_open_jobs_by_client = {
      no: otherJobs.length.toString(),
      list: otherJobs,
    };

    // 11. Recent History
    const historyJobs: any[] = [];
    $('[data-test="WorkHistory"] article, [data-qa="client-recent-history"] article').each((_, el) => {
      historyJobs.push({
        name: $(el).find('h4, .job-title').first().text().trim(),
        job_link: $(el).find('a').first().attr('href') || null,
        start_date: $(el).find('.date, [data-qa="start-date"]').text().trim(),
        no_of_hours: $(el).find('.hours').text().trim() || null,
        per_hour_rate: $(el).find('.rate').text().trim() || null,
        job_employee: $(el).find('.freelancer-name').text().trim(),
      });
    });
    jobData.client_recent_history = {
      total_numbers: historyJobs.length.toString(),
      jobs_in_progress: historyJobs,
    };

    return jobData;
  }


}
