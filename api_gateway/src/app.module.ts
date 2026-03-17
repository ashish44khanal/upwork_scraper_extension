import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { ConfigModule } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ScrapeModule } from './scrape/scrape.module';
import { JobCardEntity } from './database/entities/job-card.entity';
import { ExtractedJobEntity } from './database/entities/extracted-job.entity';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    TypeOrmModule.forRoot({
    type: 'postgres',
    host: process.env.DB_HOST || 'localhost',
    port: parseInt(process.env.DB_PORT || '5432', 10),
    username: process.env.DB_USERNAME || 'postgres',
    password: process.env.DB_PASSWORD || 'postgres',
    database: process.env.DB_NAME || 'upwork_scraper_db',
    entities: [JobCardEntity, ExtractedJobEntity],
    synchronize: false,
  }), ScrapeModule],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
