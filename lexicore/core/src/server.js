const fastify = require('fastify')({ logger: true });
const helmet = require('@fastify/helmet')

// Register helmet for security headers
fastify.register(helmet);

// Declare a route
fastify.get('/', async (request, reply) => {
  return { hello: 'world' };
});

// Run the server
const start = async () => {
  try {
    await fastify.listen({ port: 3001 });
    console.log(`Server is running on http://localhost:3001`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();