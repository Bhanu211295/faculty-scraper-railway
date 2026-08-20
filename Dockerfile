FROM python:3.11-slim

# Install system dependencies needed by Playwright
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    wget \
    ca-certificates \
    fonts-liberation \
    libc6 \
    libgcc1 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-dri3-0 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY requirements-railway.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-railway.txt

# Install Playwright browsers
RUN python -m playwright install chromium

# Copy app files
COPY streamlit_app_advanced.py .
COPY fetcher_advanced.py .
COPY extractor.py .

# Create .streamlit config directory
RUN mkdir -p ~/.streamlit

# Create Streamlit config
RUN echo "[server]\n\
headless = true\n\
port = 8501\n\
enableCORS = false" > ~/.streamlit/config.toml

# Expose port
EXPOSE 8501

# Run Streamlit
CMD ["streamlit", "run", "streamlit_app_advanced.py"]
