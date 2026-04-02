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

    // Activity on this job
    const activitySection = $('[data-test="ClientActivity"]');
    if (activitySection.length > 0) {
      const activity: any = {};
      activitySection.find('.ca-item').each((_, el) => {
        const $item = $(el);
        const title = $item.find('.title').text().trim().replace(':', '').toLowerCase();
        const value = $item.find('.value').text().trim();

        if (title.includes('proposals')) activity.proposals = value;
        else if (title.includes('last viewed')) activity.last_viewed_by_client = value;
        else if (title.includes('interviewing')) activity.interviewing = value;
        else if (title.includes('invites sent')) activity.invites_sent = value;
        else if (title.includes('unanswered invites')) activity.unanswered_invites = value;
      });
      jobData.client_activity = activity;
      
      // Sync legacy fields
      jobData.no_of_proposal_received = activity.proposals;
      jobData.no_of_invites_sent = activity.invites_sent;
    } else {
      jobData.no_of_proposal_received = $('[data-test="Proposals"] .value').text().trim() || undefined;
      jobData.no_of_invites_sent = $('[data-test="InvitesSent"] .value').text().trim() || '0';
    }

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
    const ratingElem = $('[data-testid="buyer-rating"], .rating, [data-qa="client-rating"]').first();
    if (ratingElem.length > 0) {
      const detailedText = ratingElem.find('span.nowrap, .nowrap').text().trim();
      const detailedMatch = detailedText.match(/(\d+\.?\d*)\s+of\s+(\d+)\s+reviews/);
      
      jobData.client_rating_info = {
        avg_rating: detailedMatch?.[1] || 
                    ratingElem.find('.air3-rating-value-text').text().trim() || 
                    ratingElem.find('.air3-rating-star strong').text().trim() || 
                    undefined,
        total_reviews: (detailedMatch?.[2] ? `${detailedMatch[2]} reviews` : undefined) || 
                       ratingElem.text().match(/\d+\s+review/)?.[0] || 
                       undefined,
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
    const historySection = $('[data-test="WorkHistory"]').first();
    const historyJobs: any[] = [];
    
    if (historySection.length > 0) {
      historySection.find('[data-cy="job"]').each((_, el) => {
        const $item = $(el);
        const statsText = $item.find('[data-cy="stats"]').text().trim().replace(/\s+/g, ' ');
        const amountType = statsText.includes('Fixed-price') ? 'Fixed-price' : (statsText.includes('hrs') ? 'Hourly' : null);
        
        // Amount extraction
        let amount: string | null = null;
        if (amountType === 'Fixed-price') {
            amount = statsText.match(/\$\d+\.?\d*/)?.[0] || null;
        } else if (amountType === 'Hourly') {
            amount = statsText.match(/Billed:\s*(\$\d+\.?\d*)/)?.[1] || statsText.match(/\$\d+\.?\d*/)?.[0] || null;
        }

        historyJobs.push({
          job_title: $item.find('[data-cy="job-title"]').text().trim(),
          job_link: $item.find('[data-cy="job-title"]').attr('href') || null,
          project_date_timeline: $item.find('[data-test="Stats"] .text-body-sm').first().text().trim().replace(/\s+/g, ' '),
          freelancer_rating: $item.find('.air3-rating-value-text').first().text().trim() || null,
          freelancer_name: $item.find('[data-test="FreelancerLink"] a').text().trim(),
          freelancer_feedback: $item.find('.air3-truncation span[id]').first().text().trim() || 
                               $item.find('.air3-truncation').first().text().replace('more', '').trim() ||
                               $item.find('.text-light-on-muted').first().text().trim() || 
                               null,
          amount: amount,
          amount_type: amountType
        });
      });
    }

    const historyTitle = $('[data-cy="work-history-title"]').text().trim();
    const totalHistoryCount = historyTitle.match(/\((\d+)\)/)?.[1];

    jobData.client_recent_history = {
      total_numbers: totalHistoryCount || historyJobs.length.toString(),
      jobs_in_progress: historyJobs,
    };

    return jobData;
  }


}
