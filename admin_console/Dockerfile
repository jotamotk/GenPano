FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Use Alibaba Cloud PyPI mirror
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

COPY app.py .
COPY topic_plan.py .
COPY prompt_matrix.py .
COPY segment_profiles.py .
COPY hotspot_collectors.py .
COPY _layer_classifier.py .
COPY templates/ ./templates/
COPY scripts/ ./scripts/

EXPOSE 5000

CMD ["python", "app.py"]
