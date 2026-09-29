FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/
COPY seed/ /seed/
ENV SEED_DIR=/seed

# Run as a normal user, not root
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["sh", "start.sh"]
