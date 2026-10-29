# Backend image. Build from the repository root:
#   docker build -t evacuatesim-backend -f backend/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

COPY backend/pyproject.toml backend/README* ./
COPY backend/app ./app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" "pydantic==2.12.5" \
    pydantic-settings sqlalchemy numpy

ENV EVACUATESIM_DATABASE_URL=sqlite:////data/evacuatesim.db
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
