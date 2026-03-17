import { ApiProperty } from "@nestjs/swagger";
import { IsEnum, IsNotEmpty, IsString } from "class-validator";

export class CreateScrapeDto {
    @ApiProperty({
        enum: ['manual', 'llm']
    })
    @IsNotEmpty()
    @IsEnum(['manual', 'llm'])
    extraction_mode: string;

    @ApiProperty()
    @IsNotEmpty()
    @IsString()
    page_url: string;
}
