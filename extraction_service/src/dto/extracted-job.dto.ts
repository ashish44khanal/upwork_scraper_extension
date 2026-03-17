import { IsString, IsOptional, IsBoolean, IsArray, IsObject, IsDateString } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class ExtractedJobDto {
  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  job_title?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  job_published_info?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  job_location_info?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  job_summary?: string;

  @ApiProperty({ required: false })
  @IsBoolean()
  @IsOptional()
  is_featured_job?: boolean;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  product_duration?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  hourly_commitment?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  project_type?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  experience_level?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  client_location?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  total_jobs_published_so_far?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  hire_rate?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  no_of_current_opening_jobs_by_client?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  total_spent?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  avg_hourly_rate_paid?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  total_paid_hours?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  client_account_active_date?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  no_of_proposal_received?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  no_of_invites_sent?: string;

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  talent_type?: string;

  @ApiProperty({ type: [String], required: false })
  @IsArray()
  @IsOptional()
  list_of_skills_and_expertise_required_for_the_job?: string[];

  @ApiProperty({ required: false })
  @IsObject()
  @IsOptional()
  client_rating_info?: {
    total_reviews?: string;
    avg_rating?: string;
  };

  @ApiProperty({ required: false })
  @IsObject()
  @IsOptional()
  other_open_jobs_by_client?: {
    no?: string;
    list?: Array<{
      job_title: string;
      link: string;
    }>;
  };

  @ApiProperty({ required: false })
  @IsObject()
  @IsOptional()
  client_recent_history?: {
    total_numbers?: string;
    jobs_in_progress?: Array<{
      name: string;
      job_link: string | null;
      start_date: string;
      no_of_hours: string | null;
      per_hour_rate: string | null;
      job_employee: string;
    }>;
  };

  @ApiProperty({ required: false })
  @IsString()
  @IsOptional()
  scraped_at?: string;
}
