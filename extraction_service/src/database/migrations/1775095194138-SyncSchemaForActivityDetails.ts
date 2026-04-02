import { MigrationInterface, QueryRunner } from "typeorm";

export class SyncSchemaForActivityDetails1775095194138 implements MigrationInterface {
    name = 'SyncSchemaForActivityDetails1775095194138'

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "extracted_jobs" ADD "client_activity" jsonb`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "extracted_jobs" DROP COLUMN "client_activity"`);
    }

}
