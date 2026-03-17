import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { GoogleGenerativeAI, SchemaType } from '@google/generative-ai';
import { ExtractedJobDto } from '../dto/extracted-job.dto';

@Injectable()
export class GeminiService {
  private readonly logger = new Logger(GeminiService.name);
  private genAI: GoogleGenerativeAI;
  private model: any;

  constructor(private configService: ConfigService) {
    const apiKey = this.configService.get<string>('GEMINI_API_KEY');
    this.logger.debug(`Loading Gemini API Key: ${apiKey ? 'Found' : 'NOT FOUND'}`);
    if (apiKey) {
      this.genAI = new GoogleGenerativeAI(apiKey);
      this.model = this.genAI.getGenerativeModel({
        model: 'models/gemini-1.5-flash',
        generationConfig: {
          responseMimeType: 'application/json',
          responseSchema: {
            type: SchemaType.OBJECT,
            properties: {
              job_title: { type: SchemaType.STRING },
              job_summary: { type: SchemaType.STRING },
              job_published_info: { type: SchemaType.STRING },
              job_location_info: { type: SchemaType.STRING },
              is_featured_job: { type: SchemaType.BOOLEAN },
              product_duration: { type: SchemaType.STRING },
              hourly_commitment: { type: SchemaType.STRING },
              project_type: { type: SchemaType.STRING },
              experience_level: { type: SchemaType.STRING },
              client_location: { type: SchemaType.STRING },
              total_jobs_published_so_far: { type: SchemaType.STRING },
              hire_rate: { type: SchemaType.STRING },
              no_of_current_opening_jobs_by_client: { type: SchemaType.STRING },
              total_spent: { type: SchemaType.STRING },
              avg_hourly_rate_paid: { type: SchemaType.STRING },
              total_paid_hours: { type: SchemaType.STRING },
              client_account_active_date: { type: SchemaType.STRING },
              no_of_proposal_received: { type: SchemaType.STRING },
              no_of_invites_sent: { type: SchemaType.STRING },
              talent_type: { type: SchemaType.STRING },
              list_of_skills_and_expertise_required_for_the_job: {
                type: SchemaType.ARRAY,
                items: { type: SchemaType.STRING },
              },
              client_rating_info: { type: SchemaType.STRING },
              other_open_jobs_by_client: { type: SchemaType.STRING },
              client_recent_history: { type: SchemaType.STRING },
            },
          },
        },
      });
    }
  }

  async extractData(html: string): Promise<ExtractedJobDto> {
    if (!this.model) {
      throw new Error('Gemini API key not configured');
    }

    try {
      // Basic semantic chunking: Extract relevant text content if HTML is too large
      // For now, we pass the HTML directly as Gemini 1.5 has a large context window.
      // If it fails, we can implement more aggressive stripping.
      const prompt = `
        Extract structured information from the following Upwork job listing HTML.
        Focus on job details, client information, activity, and required skills.
        Return the data in the specified JSON format.
        
        HTML:
        ${html}
      `;

      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      return JSON.parse(response.text());
    } catch (error) {
      this.logger.error(`Error extracting data with Gemini: ${error.message}`);
      throw error;
    }
  }
}
