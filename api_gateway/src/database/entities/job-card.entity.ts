import { Entity, Column, PrimaryColumn, PrimaryGeneratedColumn, CreateDateColumn, UpdateDateColumn } from 'typeorm';

@Entity('job_cards')
export class JobCardEntity {
  @PrimaryGeneratedColumn({ type: 'bigint' })
  id: string;

  @Column({ name: 'event_id', type: 'varchar', length: 50 })
  event_id: string;

  @Column({ name: 'url', type: 'text' })
  url: string;

  @Column({ name: 'status', type: 'varchar', length: 20 })
  status: string;

  @Column({ name: 'html_content', type: 'text' })
  html_content: string;

  @Column({ name: 'metadata_json', type: 'json', nullable: true })
  metadata_json: Record<string, any>;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;
}
