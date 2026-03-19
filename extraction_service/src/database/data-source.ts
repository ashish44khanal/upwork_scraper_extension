import 'reflect-metadata';
import { DataSource } from 'typeorm';
import * as dotenv from 'dotenv';
import * as path from 'path';
import { JobCardEntity } from '../entities/job-card.entity';
import { ExtractedJobEntity } from '../entities/extracted-job.entity';

dotenv.config();

console.log(`📡 Connecting to Database at ${process.env.DB_HOST || 'localhost'}:${process.env.DB_PORT || '5432'}`);

export const AppDataSource = new DataSource({
  type: 'postgres',
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '5432', 10),
  username: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'postgres',
  database: process.env.DB_NAME || 'upwork_db',
  synchronize: false,
  logging: true,
  entities: [JobCardEntity, ExtractedJobEntity],
  migrations: [path.join(__dirname, 'migrations/*{.ts,.js}')],
  subscribers: [],
});
