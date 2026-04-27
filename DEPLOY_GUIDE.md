# 部署和测试指南

## 当前状态

最新代码已推送到 GitHub (commit: 7392ae1)
- 修改内容：将页面加载策略从 networkidle 改回 commit，避免超时问题

## CI/CD 状态

等待 GitHub Actions 完成构建...

## 服务器部署步骤

### 1. 拉取最新镜像并重启服务
```bash
ssh root@116.62.36.173
cd /app
docker-compose pull
docker-compose up -d
```

### 2. 触发豆包查询测试
```bash
# 在服务器上执行
cd /app
python3 trigger_doubao_remote.py
```

### 3. 如果没有 PENDING 的豆包查询，先创建一些
```python
# 在服务器上运行 Python
import os
os.environ['PYTHONPATH'] = '/app'
from sqlalchemy import select
from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import Query
import asyncio

async def create_doubao_queries():
    task_engine = create_task_engine()
    async with get_task_async_session(task_engine) as db:
        test_queries = [
            "什么是人工智能？",
            "如何学习编程？",
            "推荐一本好书",
            "今天天气怎么样？",
            "怎么做番茄炒蛋？",
            "介绍一下北京",
            "什么是机器学习？",
            "如何保持健康？",
            "推荐一部电影",
            "解释一下量子计算"
        ]
        for q_text in test_queries:
            q = Query(
                query_text=q_text,
                target_llm='doubao',
                status='PENDING',
                brand_id=999
            )
            db.add(q)
        await db.commit()
    await task_engine.dispose()

asyncio.run(create_doubao_queries())
```

### 4. 查看查询进度
访问 http://116.62.36.173/query/ 查看查询结果

### 5. 查看 Worker 日志
```bash
docker-compose logs -f worker
```
