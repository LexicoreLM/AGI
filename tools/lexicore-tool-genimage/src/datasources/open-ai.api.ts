import OpenAI from 'openai';
class OpenAIApi {
  private openAiClient;
  constructor() {
    const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
    this.openAiClient = new OpenAI({ apiKey: OPENAI_API_KEY });
  }
  async generateImage(prompt: string): Promise<string> {
    const response = await this.openAiClient.images.generate({
      model: 'dall-e-3',
      prompt,
      n: 1,
    });
    return response.data[0].url;
  }
}

export const openAIApiInstance = new OpenAIApi();
