import './config/env.js';
import Fastify from 'fastify';

import genImageRoutes from './routes/gen-image.route.js';

const fastify = Fastify({
  logger: true,
});
fastify.register(genImageRoutes);

const port = Number(process.env.PORT || '3000');
const start = async () => {
  try {
    await fastify.listen({ port: port });
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};
start();
