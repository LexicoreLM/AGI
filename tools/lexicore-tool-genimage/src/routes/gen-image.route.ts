import { openAIApiInstance } from '../datasources/open-ai.api.js';
import fs from 'fs';
import { FastifyReply } from 'fastify';

async function genImageRoutes(fastify, options) {
  fastify.get('/gen-image/about', (request, reply) => {
    const stream = fs.createReadStream('src/assets/about.md');
    reply.type('text/html').send(stream);
  });

  fastify.get('/gen-image/schema', (request, reply: FastifyReply) => {
    const stream = fs.createReadStream('src/assets/open-api.json');
    reply.type('application/json').send(stream);
  });

  fastify.post('/gen-image/generate', async (request, reply) => {
    const url = await openAIApiInstance.generateImage(request.body.prompt);
    return { imageUrl: url };
  });
}

export default genImageRoutes;
