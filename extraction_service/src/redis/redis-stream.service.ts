import { Injectable, OnModuleInit, OnModuleDestroy, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Redis from 'ioredis';
import { ManualExtractionService } from '../extraction/manual-extraction.service';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { ExtractedJobEntity } from '../entities/extracted-job.entity';
import { JobCardEntity } from '../entities/job-card.entity';

@Injectable()
export class RedisStreamService implements OnModuleInit, OnModuleDestroy {
  private redis: Redis;
  private readonly logger = new Logger(RedisStreamService.name);
  private isRunning = false;
  private readonly batchSize = 5; // Handle multiple events in parallel

  constructor(
    private configService: ConfigService,
    private extractionService: ManualExtractionService,
    @InjectRepository(ExtractedJobEntity)
    private readonly jobRepository: Repository<ExtractedJobEntity>,
    @InjectRepository(JobCardEntity)
    private readonly jobCardRepository: Repository<JobCardEntity>,
  ) {
    this.redis = new Redis({
      host: this.configService.get<string>('REDIS_HOST', 'localhost'),
      port: this.configService.get<number>('REDIS_PORT', 6379),
    });
  }

  async onModuleInit() {
    this.isRunning = true;
    this.listenToStream();
    this.processBacklog();
  }

  onModuleDestroy() {
    this.isRunning = false;
    this.redis.disconnect();
  }

  /**
   * Process any jobs that are stuck in 'captured' state in the DB on startup.
   * This ensures we process backlog even if Redis stream events were lost or trimmed.
   */
  async processBacklog() {
    this.logger.log('Starting backlog processing for captured jobs...');
    try {
      // Fetch all validation jobs that are captured but not extracted
      const pendingJobs = await this.jobCardRepository.find({
        where: { status: 'captured' },
        select: ['event_id'] 
      });

      this.logger.log(`Found ${pendingJobs.length} pending jobs in backlog.`);

      for (const job of pendingJobs) {
        if (!this.isRunning) break;
        await this.processJob(job.event_id);
      }
      this.logger.log('Backlog processing completed.');
    } catch (err) {
      this.logger.error(`Error processing backlog: ${err.message}`);
    }
  }

  private async listenToStream() {
    const streamName = 'upwork_job_extraction_stream';
    const groupName = 'extraction_service_group';
    const consumerName = `consumer_${process.pid}`;

    try {
      await this.redis.xgroup('CREATE', streamName, groupName, '$', 'MKSTREAM').catch(() => {});

      while (this.isRunning) {
        const response = await this.redis.xreadgroup(
          'GROUP', groupName, consumerName,
          'COUNT', this.batchSize,
          'BLOCK', 5000,
          'STREAMS', streamName, '>'
        );

        if (response && (response as any).length > 0) {
          const messages = (response as any)[0][1];
          
          await Promise.all(messages.map(async ([streamId, fields]) => {
            const eventId = fields[1]; // Assuming 'status' is field[0], val is field[1]... wait, XADD ID KEY VAL
            // Actually fields is array [key, val, key, val]. 
            // We pushed: xadd(stream, id, 'status', 'captured') -> id is the EventID (if we used it as ID) OR
            // If we used auto-ID, the eventID is usually in the body or the ID itself is the eventID?
            
            // In trigger script: await redis.xadd(streamName, newId, 'status', 'captured');
            // keys: ['status', 'captured']. The ID of message is newId.
            // So streamId IS the eventId in our current design.
            
            await this.processJob(streamId, streamId, groupName, streamName);
          }));
        }
      }
    } catch (error) {
      this.logger.error(`Stream listener error: ${error.message}`);
      if (this.isRunning) {
        setTimeout(() => this.listenToStream(), 5000);
      }
    }
  }

  async extractByEventId(eventId: string) {
    this.logger.log(`Manually triggering extraction for event_id: ${eventId}`);
    await this.processJob(eventId);
  }

  /**
   * Unified processing logic with concurrency control.
   * @param eventId The business logic ID (event_id in DB)
   * @param streamMessageId The Redis Stream Message ID (for ACK)
   * @param groupName Consumer group name (for ACK)
   * @param streamName Stream name (for ACK)
   */
  private async processJob(eventId: string, streamMessageId?: string, groupName?: string, streamName?: string) {
    try {
      this.logger.log(`Processing job ${eventId} (StreamMsg: ${streamMessageId || 'N/A'})`);

      // 1. Attempt to lock the job by updating status to 'processing'
      // This prevents race conditions between Stream and Backlog processor
      const updateResult = await this.jobCardRepository.update(
        { event_id: eventId, status: 'captured' },
        { status: 'processing' }
      );

      if (updateResult.affected === 0) {
        // Validation: Check if it's already extracted or processing
        const currentJob = await this.jobCardRepository.findOne({ where: { event_id: eventId } });
        if (currentJob) {
             if (currentJob.status === 'extracted') {
                this.logger.log(`Job ${eventId} already extracted. Skipping.`);
                if (streamMessageId && groupName && streamName) {
                    await this.redis.xack(streamName, groupName, streamMessageId);
                }
                return;
             }
             if (currentJob.status === 'processing') {
                 // Another consumer/process is handling it.
                 this.logger.log(`Job ${eventId} is currently being processed by another worker.`);
                 return;
             }
        } else {
             this.logger.warn(`Job ${eventId} not found in DB.`);
             if (streamMessageId && groupName && streamName) {
                // If not in DB, we can't extract. Ack to remove from pending? Or keep?
                // For now, Ack to avoid infinite loops if it's a ghost event.
                await this.redis.xack(streamName, groupName, streamMessageId);
             }
             return;
        }
      }

      // 2. Fetch locked job
      const jobCard = await this.jobCardRepository.findOne({ where: { event_id: eventId } });
      if (!jobCard) return; // Should not happen given update check

      // 3. Extract
      this.logger.log(`Starting extraction for ${eventId}...`);
      const extractedData = await this.extractionService.extractData(jobCard.html_content);

      // 4. Save and Update Status
      await this.jobRepository.manager.transaction(async (transactionalEntityManager) => {
        const entity = this.jobRepository.create({
          ...extractedData,
          event_id: eventId,
          job_url: jobCard.url,
          scraped_at: new Date(),
        });

        await transactionalEntityManager.save(entity);
        await transactionalEntityManager.update(JobCardEntity, { id: jobCard.id }, { status: 'extracted' });
      });

      // 5. Ack Stream if applicable
      if (streamMessageId && groupName && streamName) {
        await this.redis.xack(streamName, groupName, streamMessageId);
      }

      this.logger.log(`Successfully extracted job: ${eventId}`);

    } catch (err) {
      this.logger.error(`Error processing job ${eventId}: ${err.message}`);
      // Revert status to 'captured' so it can be retried?
      // For now, leave as processing or maybe 'failed'.
      // Only revert if we want retry.
      await this.jobCardRepository.update({ event_id: eventId }, { status: 'captured' });
    }
  }
}
