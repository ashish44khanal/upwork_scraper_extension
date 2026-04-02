import { Controller, Get, Post, Body, Patch, Param, Delete, Query, Res } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiQuery, ApiResponse } from '@nestjs/swagger';
import type { Response } from 'express';
import { ScrapeService } from './scrape.service';
import { CreateScrapeDto } from './dto/create-scrape.dto';
import { UpdateScrapeDto } from './dto/update-scrape.dto';
import { ExtractedJobEntity } from '../database/entities/extracted-job.entity';

@ApiTags('scrape')
@Controller('scrape')
export class ScrapeController {
  constructor(private readonly scrapeService: ScrapeService) {}

  @Post('/upwork_jobs')
  create(@Body() createScrapeDto: CreateScrapeDto) {
    return this.scrapeService.create(createScrapeDto);
  }

  @Get('/data')
  @ApiOperation({ summary: 'Get all extracted job data' })
  @ApiQuery({ name: 'url', required: false, description: 'Filter by job URL or parent URL' })
  @ApiQuery({ name: 'page', required: false, type: Number })
  @ApiQuery({ name: 'limit', required: false, type: Number })
  @ApiResponse({ 
    status: 200, 
    description: 'List of extracted jobs with pagination',
    schema: {
      properties: {
        data: { type: 'array', items: { $ref: '#/components/schemas/ExtractedJobEntity' } },
        total: { type: 'number' },
        page: { type: 'number' },
        lastPage: { type: 'number' }
      }
    }
  })
  findData(
    @Query('url') url?: string,
    @Query('page') page: number = 1,
    @Query('limit') limit: number = 10,
  ) {
    return this.scrapeService.findExtractedValues({ url, page: +page, limit: +limit });
  }

  @Get('/download-csv')
  async downloadCsv(
    @Query('url') url: string,
    @Res() res: Response,
  ) {
    const csv = await this.scrapeService.getExtractedDataForCsv(url);
    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', 'attachment; filename=scraped_data.csv');
    return res.status(200).send(csv);
  }

  @Get()
  findAll() {
    return this.scrapeService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.scrapeService.findOne(+id);
  }

  @Patch(':id')
  update(@Param('id') id: string, @Body() updateScrapeDto: UpdateScrapeDto) {
    return this.scrapeService.update(+id, updateScrapeDto);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.scrapeService.remove(+id);
  }
}
