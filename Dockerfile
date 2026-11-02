# Runs Big CSV Explorer on any Docker host:
# Hugging Face Spaces (Docker SDK), Render, Railway, Fly.io, a VM ...
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces uses port 7860; Render/Railway pass $PORT.
ENV PORT=7860
EXPOSE 7860

# XSRF/CORS off: needed for file uploads behind the hosts' proxies.
CMD ["sh", "-c", "python app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --server.enableXsrfProtection=false --server.enableCORS=false"]
