FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python scripts/generate_once.py --all || true
EXPOSE 8787
CMD ["uvicorn","backend.app.main:app","--host","0.0.0.0","--port","8787"]
