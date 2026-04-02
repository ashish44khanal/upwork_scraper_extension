import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { JobCardEntity } from '../database/entities/job-card.entity';
import { ExtractedJobEntity } from '../database/entities/extracted-job.entity';
import { ScrapeService } from './scrape.service';

describe('ScrapeService', () => {
  let service: ScrapeService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ScrapeService,
        {
          provide: 'REDIS_CLIENT',
          useValue: {
            xadd: jest.fn(),
          },
        },
        {
          provide: getRepositoryToken(JobCardEntity),
          useValue: {
            find: jest.fn(),
            createQueryBuilder: jest.fn(),
          },
        },
        {
          provide: getRepositoryToken(ExtractedJobEntity),
          useValue: {
            createQueryBuilder: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get<ScrapeService>(ScrapeService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });
});
