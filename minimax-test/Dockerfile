FROM mcr.microsoft.com/playwright:v1.42.0-jammy

WORKDIR /app

COPY package*.json ./
RUN npm install

# Install Chromium browser for Playwright
RUN npx playwright install chromium

COPY . .

RUN mkdir -p uploads screenshots

EXPOSE 3099

CMD ["node", "server.js"]
