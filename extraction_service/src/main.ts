import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { MicroserviceOptions, Transport } from '@nestjs/microservices';

import { ValidationPipe } from '@nestjs/common';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';

async function bootstrap() {
  const app = await NestFactory.createMicroservice<MicroserviceOptions>(AppModule, {
    transport: Transport.REDIS,
    options: {
      host: process.env.REDIS_HOST || 'localhost',
      port: parseInt(process.env.REDIS_PORT || '6379', 10),
    },
  });

  // Enable validation
  app.useGlobalPipes(new ValidationPipe({ transform: true }));

  // Note: Swagger typically runs on HTTP. If this is strictly a microservice, 
  // Swagger won't be accessible unless we also create an HTTP app.
  // The user asked to use swagger, so I'll keep the DTO annotations.

  await app.listen();
}
bootstrap();
