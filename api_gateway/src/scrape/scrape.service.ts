import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Repository } from 'typeorm';
import { InjectRepository } from '@nestjs/typeorm';
import { JobCardEntity } from '../database/entities/job-card.entity';
import { ExtractedJobEntity } from '../database/entities/extracted-job.entity';
import { CreateScrapeDto } from './dto/create-scrape.dto';
import Redis from 'ioredis';
import * as crypto from 'crypto';

@Injectable()
export class ScrapeService {
  private readonly logger = new Logger(ScrapeService.name);

  constructor(
    @Inject('REDIS_CLIENT') private readonly redis: Redis,
    @InjectRepository(JobCardEntity)
    private readonly jobCardRepo: Repository<JobCardEntity>,
    @InjectRepository(ExtractedJobEntity)
    private readonly extractedJobRepo: Repository<ExtractedJobEntity>,
    private readonly configService: ConfigService,
  ) {}

  async create(dto: CreateScrapeDto) {
    try {
      const rawUrl = dto.page_url || (dto as any).url;
      if (!rawUrl) {
        throw new Error('URL is required for scraping');
      }
      const url = String(rawUrl);

      // 1. Generate a unique lock key for this URL
      const urlHash = crypto.createHash('md5').update(url).digest('hex');
      const lockKey = `scrape_lock:${urlHash}`;

      // 2. Check if a lock already exists
      const existingJobId = await this.redis.get(lockKey);
      if (existingJobId) {
        this.logger.log(`[ScrapeService] URL already being processed. Returning existing Job ID: ${existingJobId}`);
        return { id: existingJobId, stream: 'upwork_jobs_stream', ...dto, already_processing: true };
      }

      const stream = this.configService.get<string>('REDIS_JOBS_STREAM_NAME', 'upwork_jobs_stream');
      const id = await this.redis.xadd(stream, 'MAXLEN', '~', 10000, '*', ...Object.entries(dto).flat());
      if (!id) {
        throw new Error('Failed to create Redis stream event: ID is null');
      }
      
      // 3. Set the lock with a 15-minute TTL (safety buffer)
      // The lock will be released by the extraction service upon completion
      await this.redis.set(lockKey, id, 'EX', 900); 

      this.logger.log(`[ScrapeService] Job created in stream ${stream}: ${id}`);
      return { id, stream, ...dto };
    } catch (error) {
      this.logger.error(`[ScrapeService] Failed to create scrape job: ${error.message}`);
      throw error;
    }
  }

  async findExtractedValues(query: { url?: string; page?: number; limit?: number }) {
    const { url, page = 1, limit = 10 } = query;
    const skip = (page - 1) * limit;

    // Normalize URL: trim, remove trailing slash, and handle space encoding variations
    const normalizedUrl = url?.trim().replace(/\/$/, '').replace(/%20/g, '+');
    console.log(`[ScrapeService] Filtering by URL: "${url}" (Normalized: "${normalizedUrl}")`);

    const queryBuilder = this.extractedJobRepo.createQueryBuilder('ej')
      .innerJoinAndSelect(JobCardEntity, 'jc', 'jc.event_id = ej.event_id');

    if (url && url.trim() !== '') {
      // Use ILIKE for both and be more permissive with metadata search
      queryBuilder.andWhere('(ej.job_url ILIKE :url OR jc.url ILIKE :url OR jc.metadata_json->>\'parent_url\' ILIKE :url)', { 
        url: `%${normalizedUrl}%`
      });
    }

    const [data, total] = await queryBuilder
      .orderBy('ej.scraped_at', 'DESC')
      .skip(skip)
      .take(limit)
      .getManyAndCount();

    // TypeORM getManyAndCount on ej will only return ej properties.
    // To include jc.url in the result, we might need a raw query or a mapping.
    // For now, let's just make sure we get the items.
    
    return {
      data,
      total,
      page,
      lastPage: Math.ceil(total / limit),
    };
  }

  findAll() {
    return this.jobCardRepo.find({
      order: { created_at: 'DESC' },
      take: 50,
    });
  }

  async getExtractedDataForCsv(url: string): Promise<string> {
    const queryBuilder = this.extractedJobRepo.createQueryBuilder('ej')
      .innerJoin(JobCardEntity, 'jc', 'jc.event_id = ej.event_id')
      .select([
        'ej.*',
      ]);

    const normalizedUrl = url?.trim().replace(/%20/g, '+');
    if (url && url.trim() !== '') {
      queryBuilder.andWhere('(jc.url ILIKE :url OR jc.metadata_json->>\'parent_url\' ILIKE :url)', { 
        url: `%${normalizedUrl}%`
      });
    }

    const data = await queryBuilder
      .orderBy('ej.scraped_at', 'DESC')
      .getRawMany();

    if (data.length === 0) {
      return '';
    }

    // Define headers for CSV
    const headers = [
      'ID', 'URL', 'Job Title', 'Published Info', 'Location', 'Summary', 
      'Is Featured', 'Duration', 'Commitment', 'Project Type', 'Experience Level', 
      'Client Location', 'Jobs Published', 'Hire Rate', 'Total Spent', 
      'Avg Hourly Rate', 'Total Paid Hours', 'Account Active Date', 
      'Proposals Received', 'Invites Sent', 'Talent Type', 'Skills', 
      'Total Reviews', 'Avg Rating', 'Scraped At'
    ];

    const rows = data.map(item => {
      // Handle the complex fields from raw query
      // Note: getRawMany might return strings for some types depending on the driver
      let skills = '';
      try {
        const skillsObj = typeof item.list_of_skills_and_expertise_required_for_the_job === 'string'
          ? JSON.parse(item.list_of_skills_and_expertise_required_for_the_job)
          : item.list_of_skills_and_expertise_required_for_the_job;
        skills = Array.isArray(skillsObj) ? skillsObj.join(', ') : '';
      } catch (e) {
        skills = '';
      }

      let ratingInfo = { total_reviews: '', avg_rating: '' };
      try {
        ratingInfo = typeof item.client_rating_info === 'string'
          ? JSON.parse(item.client_rating_info)
          : item.client_rating_info || {};
      } catch (e) {}

      const fields = [
        item.id,
        item.job_url,
        item.job_title,
        item.job_published_info,
        item.job_location_info,
        item.job_summary?.replace(/\n/g, ' '),
        item.is_featured_job,
        item.product_duration,
        item.hourly_commitment,
        item.project_type,
        item.experience_level,
        item.client_location,
        item.total_jobs_published_so_far,
        item.hire_rate,
        item.total_spent,
        item.avg_hourly_rate_paid,
        item.total_paid_hours,
        item.client_account_active_date,
        item.no_of_proposal_received,
        item.no_of_invites_sent,
        item.talent_type,
        skills,
        ratingInfo.total_reviews,
        ratingInfo.avg_rating,
        item.scraped_at
      ];

      return fields.map(val => {
        const str = String(val ?? '');
        return `"${str.replace(/"/g, '""')}"`;
      }).join(',');
    });

    return [headers.join(','), ...rows].join('\n');
  }

  async getExtractionSummary(url: string) {
    // Normalize URL: trim, remove trailing slash, and handle space encoding variations
    const normalizedUrl = url?.trim().replace(/\/$/, '').replace(/%20/g, '+');
    const urlFilter = `%${normalizedUrl}%`;

    // Get all job cards matching this scrape URL
    const cardStats = await this.jobCardRepo
      .createQueryBuilder('jc')
      .select('jc.status', 'status')
      .addSelect('COUNT(*)::int', 'count')
      .where("jc.url ILIKE :url OR jc.metadata_json->>'parent_url' ILIKE :url", { url: urlFilter })
      .groupBy('jc.status')
      .getRawMany();

    const statusCounts: Record<string, number> = {};
    let totalCards = 0;
    for (const row of cardStats) {
      statusCounts[row.status] = row.count;
      totalCards += row.count;
    }

    // Get extracted job count and sample data
    const extractedCount = await this.extractedJobRepo
      .createQueryBuilder('ej')
      .innerJoin(JobCardEntity, 'jc', 'jc.event_id = ej.event_id')
      .where("jc.url ILIKE :url OR jc.metadata_json->>'parent_url' ILIKE :url", { url: urlFilter })
      .getCount();

    // Get the latest few extracted jobs for a preview
    const latestExtracted = await this.extractedJobRepo
      .createQueryBuilder('ej')
      .innerJoin(JobCardEntity, 'jc', 'jc.event_id = ej.event_id')
      .where("jc.url ILIKE :url OR jc.metadata_json->>'parent_url' ILIKE :url", { url: urlFilter })
      .orderBy('ej.scraped_at', 'DESC')
      .limit(5)
      .getMany();

    // Determine overall pipeline status
    let pipelineStatus = 'idle';
    if (totalCards === 0) {
      pipelineStatus = 'no_data';
    } else if ((statusCounts['processing'] || 0) > 0) {
      pipelineStatus = 'in_progress';
    } else if ((statusCounts['captured'] || 0) > 0) {
      pipelineStatus = 'pending_extraction';
    } else if (extractedCount === totalCards) {
      pipelineStatus = 'completed';
    } else if ((statusCounts['failed'] || 0) > 0) {
      pipelineStatus = 'partially_failed';
    } else {
      pipelineStatus = 'completed';
    }

    return {
      url: url.trim(),
      pipeline_status: pipelineStatus,
      total_cards_scraped: totalCards,
      total_extracted: extractedCount,
      card_status_breakdown: {
        captured: statusCounts['captured'] || 0,
        processing: statusCounts['processing'] || 0,
        extracted: statusCounts['extracted'] || 0,
        failed: statusCounts['failed'] || 0,
      },
      completion_rate: totalCards > 0 ? `${Math.round((extractedCount / totalCards) * 100)}%` : '0%',
      latest_extractions: latestExtracted.map(ej => ({
        event_id: ej.event_id,
        job_title: ej.job_title,
        client_location: ej.client_location,
        experience_level: ej.experience_level,
        scraped_at: ej.scraped_at,
      })),
    };
  }

  findOne(id: number) { return {} }
  update(id: number, dto: any) { return {} }
  remove(id: number) { return {} }
}
