import sys
import os
os.environ['PYTHONPATH'] = '/app'

from geo_tracker.tasks.celery_tasks import execute_query
from sqlalchemy import select
from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import Query
import asyncio

async def main():
    task_engine = create_task_engine()
    try:
        async with get_task_async_session(task_engine) as db:
            result = await db.execute(
                select(Query)
                .where(Query.target_llm == 'gemini')
                .where(Query.status == 'PENDING')
                .order_by(Query.id)
                .limit(10)
            )
            queries = result.scalars().all()

            print(f"Found {len(queries)} Gemini queries")
            for q in queries:
                print(f"  Triggering query {q.id}: {q.query_text[:50]}...")
                execute_query.apply_async(args=[q.id], queue='llm_gemini')

            if not queries:
                print("No PENDING Gemini queries found, looking for any Gemini queries...")
                result = await db.execute(
                    select(Query)
                    .where(Query.target_llm == 'gemini')
                    .order_by(Query.id.desc())
                    .limit(10)
                )
                queries = result.scalars().all()
                if queries:
                    print(f"Found {len(queries)} existing Gemini queries:")
                    for q in queries:
                        print(f"  [{q.id}] {q.status}: {q.query_text[:50]}...")

    finally:
        await task_engine.dispose()

asyncio.run(main())
