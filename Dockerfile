FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 DOCKER_CONTAINER=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY static ./static
COPY tests ./tests
COPY main.py .

# Sinh dữ liệu tổng hợp + huấn luyện + đánh giá NGAY KHI BUILD (tất định theo seed), rồi chạy test offline.
RUN python -m scripts.build_assets && LLM_API_KEY= python -m pytest -q -p no:warnings tests

EXPOSE 8080
CMD ["python", "main.py"]
