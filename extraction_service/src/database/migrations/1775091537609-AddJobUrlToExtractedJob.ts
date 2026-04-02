import { MigrationInterface, QueryRunner } from "typeorm";

export class AddJobUrlToExtractedJob1775091537609 implements MigrationInterface {
    name = 'AddJobUrlToExtractedJob1775091537609'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`DROP INDEX "public"."ix_job_cards_event_id"`);
        await queryRunner.query(`ALTER TABLE "extracted_jobs" ADD "job_url" character varying`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "extracted_jobs" DROP COLUMN "job_url"`);
        await queryRunner.query(`CREATE INDEX "ix_job_cards_event_id" ON "job_cards" ("event_id") `);
    }

}
