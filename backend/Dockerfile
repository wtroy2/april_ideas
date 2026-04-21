FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libffi-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
RUN mkdir -p staticfiles && chown appuser:appuser staticfiles

USER appuser

EXPOSE 8080

# collectstatic at runtime so secrets are available; then exec gunicorn
CMD ["sh", "-c", "python manage.py collectstatic --noinput && exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 0 backend.wsgi:application"]
