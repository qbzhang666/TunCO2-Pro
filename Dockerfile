FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[ifc,rhino]" && useradd -m app
USER app
EXPOSE 8000
CMD ["uvicorn", "tunco2pro.api:app", "--host", "0.0.0.0", "--port", "8000"]
