import { Inject, Injectable } from '@nestjs/common';
import { Repository } from 'typeorm';
import { InjectRepository } from '@nestjs/typeorm';
import { JobCardEntity } from '../database/entities/job-card.entity';
import { ExtractedJobEntity } from '../database/entities/extracted-job.entity';
import { CreateScrapeDto } from './dto/create-scrape.dto';
import Redis from 'ioredis';

@Injectable()
export class ScrapeService {
  constructor(
    @Inject('REDIS_CLIENT') private readonly redis: Redis,
    @InjectRepository(JobCardEntity)
    private readonly jobCardRepo: Repository<JobCardEntity>,
    @InjectRepository(ExtractedJobEntity)
    private readonly extractedJobRepo: Repository<ExtractedJobEntity>,
  ) {}

  async create(dto: CreateScrapeDto) {
    const stream = 'upwork_jobs_stream';
    const id = await this.redis.xadd(stream, '*', ...Object.entries(dto).flat());
    return { id, stream, ...dto };
  }

  async findExtractedValues(query: { url?: string; page?: number; limit?: number }) {
    const { url, page = 1, limit = 10 } = query;
    const skip = (page - 1) * limit;

    console.log(`[ScrapeService] Filtering by URL: "${url}"`);

    const queryBuilder = this.extractedJobRepo.createQueryBuilder('ej')
      .innerJoinAndSelect(JobCardEntity, 'jc', 'jc.event_id = ej.event_id');

    if (url && url.trim() !== '') {
      // Use ILIKE for both and be more permissive with metadata search
      queryBuilder.andWhere('(ej.job_url ILIKE :url OR jc.url ILIKE :url OR jc.metadata_json->>\'parent_url\' ILIKE :url)', { 
        url: `%${url.trim()}%`
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

    if (url && url.trim() !== '') {
      queryBuilder.andWhere('(jc.url ILIKE :url OR jc.metadata_json->>\'parent_url\' ILIKE :url)', { 
        url: `%${url.trim()}%`
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

  findOne(id: number) { return {} }
  update(id: number, dto: any) { return {} }
  remove(id: number) { return {} }
}
