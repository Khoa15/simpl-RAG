# simpl-RAG

# Requirements

```bash
conda create -n simpl-rag python=3.11 -y
conda activate simpl-rag
pip install -r requirements.txt
```

# Run

```
cd ./be
USE_MOCK_EMBEDDINGS=1 fastapi run src/main.py
docker run -d -p 6379:6379 redis:7-alpine
USE_MOCK_EMBEDDINGS=1 celery -A src.celery_worker:celery_app worker --loglevel=info
```

# Test
```
cd ./test
pytest test_api.py
locust -f test_locust.py --headless -u 500 -r 100 --run-time 1m --host http://localhost:8000
```
## Clear data test
```
celery -A src.celery_worker:celery_app purge
docker exec <redis_container_name> redis-cli FLUSHALL
```
