import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ScrapeService } from './scrape.service';
import { ScrapeController } from './scrape.controller';
import { JobCardEntity } from '../database/entities/job-card.entity';
import { ExtractedJobEntity } from '../database/entities/extracted-job.entity';
import Redis from 'ioredis';

@Module({
  imports: [TypeOrmModule.forFeature([JobCardEntity, ExtractedJobEntity])],
  controllers: [ScrapeController],
  providers: [
    ScrapeService,
    {
      provide: 'REDIS_CLIENT',
      inject: [ConfigService],
      useFactory: (config: ConfigService) => new Redis({ 
        host: config.get<string>('REDIS_HOST', 'localhost'), 
        port: config.get<number>('REDIS_PORT', 6379) 
      }),
    },
  ],
  exports: ['REDIS_CLIENT'],
})
export class ScrapeModule {}
