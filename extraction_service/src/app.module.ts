import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { ExtractedJobEntity } from './entities/extracted-job.entity';
import { JobCardEntity } from './entities/job-card.entity';
import { GeminiService } from './gemini/gemini.service';
import { RedisStreamService } from './redis/redis-stream.service';
import { ManualExtractionService } from './extraction/manual-extraction.service';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    TypeOrmModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        type: 'postgres',
        host: config.get<string>('DB_HOST', 'localhost'),
        port: config.get<number>('DB_PORT', 5432),
        username: config.get<string>('DB_USERNAME', 'postgres'),
        password: config.get<string>('DB_PASSWORD', 'postgres'),
        database: config.get<string>('DB_NAME', 'upwork_scraper_db'),
        entities: [ExtractedJobEntity, JobCardEntity],
        synchronize: false, // Don't modify existing tables
      }),
    }),
    TypeOrmModule.forFeature([ExtractedJobEntity, JobCardEntity]),
  ],
  controllers: [AppController],
  providers: [AppService, RedisStreamService, ManualExtractionService, GeminiService],
})
export class AppModule {}
