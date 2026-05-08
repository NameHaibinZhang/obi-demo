FROM node:20-slim

WORKDIR /app
COPY package.json .
RUN npm install --production

COPY app.js .
COPY proto/ ./proto/

EXPOSE 8082
CMD ["node", "app.js"]