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
      queryBuilder.andWhere('(jc.url ILIKE :url OR jc.metadata_json->>\'parent_url\' ILIKE :url)', { 
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
  findOne(id: number) { return {} }
  update(id: number, dto: any) { return {} }
  remove(id: number) { return {} }
}
