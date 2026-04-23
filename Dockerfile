# Stage 1: Build dependencies
FROM python:3.11-slim AS builder
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a user directory
COPY requirements.txt .
RUN pip install --user --no-cache-dir --upgrade pip && \
    pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.11-slim
WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN addgroup --system --gid 1001 botgroup && \
    adduser --system --uid 1001 --gid 1001 botuser

# Copy Python packages from builder
COPY --from=builder /root/.local /home/botuser/.local

# Copy application code
COPY . .

# Set ownership to non-root user
RUN chown -R botuser:botgroup /app

# Switch to non-root user
USER botuser

# Add local bin to PATH
ENV PATH=/home/botuser/.local/bin:$PATH
ENV PYTHONPATH=/app

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Use start script
CMD ["sh", "./start.sh"]
