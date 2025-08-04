FROM python:3.11-slim-bullseye
RUN apt-get update && apt-get install -y --no-install-recommends --no-install-suggests
RUN pip install --no-cache-dir --upgrade pip

WORKDIR /app

COPY ./requirements.txt /app

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8000

# CMD ["uvicorn", "src/main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["fastapi", "run", "src/main.py", "--port", "8000"]
