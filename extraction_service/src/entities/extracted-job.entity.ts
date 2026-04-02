import { Entity, Column, PrimaryGeneratedColumn, CreateDateColumn } from 'typeorm';

@Entity('extracted_jobs')
export class ExtractedJobEntity {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ nullable: true })
  event_id: string;

  @Column({ nullable: true })
  job_title: string;

  @Column({ nullable: true })
  job_published_info: string;

  @Column({ nullable: true })
  job_location_info: string;

  @Column({ type: 'text', nullable: true })
  job_summary: string;

  @Column({ type: 'boolean', nullable: true })
  is_featured_job: boolean;

  @Column({ nullable: true })
  product_duration: string;

  @Column({ nullable: true })
  hourly_commitment: string;

  @Column({ nullable: true })
  project_type: string;

  @Column({ nullable: true })
  experience_level: string;

  @Column({ nullable: true })
  client_location: string;

  @Column({ nullable: true })
  total_jobs_published_so_far: string;

  @Column({ nullable: true })
  hire_rate: string;

  @Column({ nullable: true })
  no_of_current_opening_jobs_by_client: string;

  @Column({ nullable: true })
  total_spent: string;

  @Column({ nullable: true })
  avg_hourly_rate_paid: string;

  @Column({ nullable: true })
  total_paid_hours: string;

  @Column({ nullable: true })
  client_account_active_date: string;

  @Column({ nullable: true })
  no_of_proposal_received: string;

  @Column({ nullable: true })
  no_of_invites_sent: string;

  @Column({ nullable: true })
  talent_type: string;

  @Column({ type: 'jsonb', nullable: true })
  list_of_skills_and_expertise_required_for_the_job: string[];

  @Column({ type: 'jsonb', nullable: true })
  client_rating_info: {
    total_reviews?: string;
    avg_rating?: string;
  };

  @Column({ type: 'jsonb', nullable: true })
  other_open_jobs_by_client: {
    no?: string;
    list?: Array<{
      job_title: string;
      link: string;
    }>;
  };

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



  @Column({ type: 'jsonb', nullable: true })
  client_activity: {
    proposals?: string;
    last_viewed_by_client?: string;
    interviewing?: string;
    invites_sent?: string;
    unanswered_invites?: string;
  };

  @Column({ nullable: true })
  job_url: string;

  @Column({ type: 'timestamp', nullable: true })
  scraped_at: Date | string;
}
