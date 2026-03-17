import { MigrationInterface, QueryRunner } from "typeorm";

export class InitialSchema1773719954957 implements MigrationInterface {

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE TABLE "job_cards" ("id" BIGSERIAL NOT NULL, "event_id" character varying(50) NOT NULL, "url" text NOT NULL, "status" character varying(20) NOT NULL, "html_content" text NOT NULL, "metadata_json" json, "created_at" TIMESTAMP NOT NULL DEFAULT now(), CONSTRAINT "PK_4810b52d9df46e7ef0d41beffe3" PRIMARY KEY ("id"))`);
        await queryRunner.query(`CREATE INDEX "ix_job_cards_event_id" ON "job_cards" ("event_id") `);
        await queryRunner.query(`CREATE TABLE "extracted_jobs" ("id" SERIAL NOT NULL, "event_id" character varying, "job_title" character varying, "job_published_info" character varying, "job_location_info" character varying, "job_summary" text, "is_featured_job" boolean, "product_duration" character varying, "hourly_commitment" character varying, "project_type" character varying, "experience_level" character varying, "client_location" character varying, "total_jobs_published_so_far" character varying, "hire_rate" character varying, "no_of_current_opening_jobs_by_client" character varying, "total_spent" character varying, "avg_hourly_rate_paid" character varying, "total_paid_hours" character varying, "client_account_active_date" character varying, "no_of_proposal_received" character varying, "no_of_invites_sent" character varying, "talent_type" character varying, "list_of_skills_and_expertise_required_for_the_job" jsonb, "client_rating_info" jsonb, "other_open_jobs_by_client" jsonb, "client_recent_history" jsonb, "scraped_at" TIMESTAMP, CONSTRAINT "PK_3b1b3bbca377e1be6a0a2f19858" PRIMARY KEY ("id"))`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`DROP TABLE "extracted_jobs"`);
        await queryRunner.query(`DROP INDEX "ix_job_cards_event_id"`);
        await queryRunner.query(`DROP TABLE "job_cards"`);
    }

}
