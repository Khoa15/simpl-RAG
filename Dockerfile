FROM node:lts-alpine as fe-builder
WORKDIR /fe
COPY fe/package*.json ./
RUN npm install
COPY fe/ ./
RUN npm run build

FROM python:3.11-slim-bullseye

RUN apt-get update && apt-get install -y --no-install-recommends --no-install-suggests \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY be/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY be/ .

COPY --from=fe-builder /fe/dist ./static

EXPOSE 8000

CMD ["fastapi", "run", "src/main.py", "--port", "8000"]
