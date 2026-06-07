# Start from python image
FROM python:3.13-slim

# Install dependencies: nodejs, npm, curl, supervisor
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    curl \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Install uv and gemini-cli
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    npm install -g @google/gemini-cli

# Set path for uv
ENV PATH="/root/.local/bin:$PATH"

# Set up working directory
WORKDIR /app

# Copy python dependencies
COPY pyproject.toml .

# Install python packages
RUN uv sync

# Copy frontend packages
COPY web/package*.json ./web/

# Install frontend packages
RUN cd web && npm install

# Copy project files
COPY . .

# Build Next.js
# We set NEXT_PUBLIC_ADK_API_URL so the frontend knows to call the /api-proxy
ENV NEXT_PUBLIC_ADK_API_URL=/api-proxy
RUN cd web && npm run build

# Setup supervisord
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Port 3000 is for NextJS. Railway uses PORT env var
# NextJS automatically picks up the PORT variable
EXPOSE 3000

# The default command runs supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
