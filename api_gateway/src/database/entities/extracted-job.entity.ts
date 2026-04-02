import { Entity, Column, PrimaryGeneratedColumn, CreateDateColumn } from 'typeorm';
import { ApiProperty } from '@nestjs/swagger';

@Entity('extracted_jobs')
export class ExtractedJobEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @ApiProperty({ description: 'The unique ID of the event' })
  @Column({ nullable: true })
  event_id: string;

  @ApiProperty({ description: 'The title of the job post' })
  @Column({ nullable: true })
  job_title: string;

  @ApiProperty({ description: 'Information about when the job was published' })
  @Column({ nullable: true })
  job_published_info: string;

  @ApiProperty({ description: 'Information about the job location' })
  @Column({ nullable: true })
  job_location_info: string;

  @ApiProperty({ description: 'The full summary or description of the job' })
  @Column({ type: 'text', nullable: true })
  job_summary: string;

  @ApiProperty({ description: 'Whether the job is featured' })
  @Column({ type: 'boolean', nullable: true })
  is_featured_job: boolean;

  @ApiProperty({ description: 'Duration of the project' })
  @Column({ nullable: true })
  product_duration: string;

  @ApiProperty({ description: 'Hourly commitment required' })
  @Column({ nullable: true })
  hourly_commitment: string;

  @ApiProperty({ description: 'Type of the project' })
  @Column({ nullable: true })
  project_type: string;

  @ApiProperty({ description: 'Experience level required' })
  @Column({ nullable: true })
  experience_level: string;

  @ApiProperty({ description: 'Location of the client' })
  @Column({ nullable: true })
  client_location: string;

  @ApiProperty({ description: 'Total jobs published by the client so far' })
  @Column({ nullable: true })
  total_jobs_published_so_far: string;

  @ApiProperty({ description: 'The client hire rate' })
  @Column({ nullable: true })
  hire_rate: string;

  @ApiProperty({ description: 'Number of current open jobs by the client' })
  @Column({ nullable: true })
  no_of_current_opening_jobs_by_client: string;

  @ApiProperty({ description: 'Total spent by the client' })
  @Column({ nullable: true })
  total_spent: string;

  @ApiProperty({ description: 'Average hourly rate paid by the client' })
  @Column({ nullable: true })
  avg_hourly_rate_paid: string;

  @ApiProperty({ description: 'Total paid hours for the client' })
  @Column({ nullable: true })
  total_paid_hours: string;

  @ApiProperty({ description: 'The date the client account became active' })
  @Column({ nullable: true })
  client_account_active_date: string;

  @ApiProperty({ description: 'Number of proposals received for the job' })
  @Column({ nullable: true })
  no_of_proposal_received: string;

  @ApiProperty({ description: 'Number of invites sent by the client' })
  @Column({ nullable: true })
  no_of_invites_sent: string;

  @ApiProperty({ description: 'Type of talent requested' })
  @Column({ nullable: true })
  talent_type: string;

  @ApiProperty({ description: 'List of skills and expertise required', type: [String] })
  @Column({ type: 'jsonb', nullable: true })
  list_of_skills_and_expertise_required_for_the_job: string[];

  @ApiProperty({ description: 'Rating information for the client' })
  @Column({ type: 'jsonb', nullable: true })
  client_rating_info: {
    total_reviews?: string;
    avg_rating?: string;
  };

  @ApiProperty({ description: 'Other open jobs by this client' })
  @Column({ type: 'jsonb', nullable: true })
  other_open_jobs_by_client: {
    no?: string;
    list?: Array<{
      job_title: string;
      link: string;
    }>;
  };

  @ApiProperty({ description: 'Recent work history for the client' })
  @Column({ type: 'jsonb', nullable: true })
  client_recent_history: {
    total_numbers?: string;
    jobs_in_progress?: Array<{
      job_title: string;
      job_link: string | null;
      project_date_timeline: string;
      freelancer_rating: string | null;
      freelancer_name: string;
      freelancer_feedback: string | null;
      amount: string | null;
      amount_type: string | null;
    }>;
  };

  @ApiProperty({ description: 'Detailed activity info on this job' })
  @Column({ type: 'jsonb', nullable: true })
  client_activity: {
    proposals?: string;
    last_viewed_by_client?: string;
    interviewing?: string;
    invites_sent?: string;
    unanswered_invites?: string;
  };

  @ApiProperty({ description: 'The original job post URL on Upwork' })
  @Column({ nullable: true })
  job_url: string;

  @ApiProperty({ description: 'Timestamp of the scraping operation' })
  @Column({ type: 'timestamp', nullable: true })
  scraped_at: Date | string;
}
