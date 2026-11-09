# Backend image. Build from the repository root:
#   docker build -t evacuatesim-backend -f backend/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .

ENV EVACUATESIM_DATABASE_URL=sqlite:////data/evacuatesim.db
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
