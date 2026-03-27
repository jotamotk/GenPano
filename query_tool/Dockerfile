FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Use Alibaba Cloud PyPI mirror
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

COPY app.py .

EXPOSE 5000

CMD ["python", "app.py"]
