FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md /app/
RUN pip install --no-cache-dir -U pip wheel && pip install --no-cache-dir -e .

COPY src/ /app/src/

ENV PORT=8081
EXPOSE 8081
CMD ["uvicorn", "datastore.service.app:app", "--host", "0.0.0.0", "--port", "8081"]
