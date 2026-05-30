FROM python:3.13.3-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARRANGER_CONFIG=/config/arranger.yaml

WORKDIR /app
COPY pyproject.toml README.md ./
COPY arranger ./arranger
RUN pip install --no-cache-dir .

RUN mkdir -p /config /data /logs
EXPOSE 8787
CMD ["python", "-m", "arranger"]
