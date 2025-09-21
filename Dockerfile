# Dockerfile.proxy
FROM node:18-alpine

WORKDIR /app

# Install dependencies
RUN npm install express cors node-fetch@2

# Copy proxy server
COPY server.js .

EXPOSE 4000

CMD ["node", "server.js"]
