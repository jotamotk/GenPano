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
            # First check for PENDING
            result = await db.execute(
                select(Query)
                .where(Query.target_llm == 'gemini')
                .where(Query.status == 'PENDING')
                .order_by(Query.id)
                .limit(3)
            )
            queries = result.scalars().all()

            if queries:
                print(f"Found {len(queries)} PENDING Gemini queries")
                for q in queries:
                    print(f"  Triggering query {q.id}: {q.query_text[:50]}...")
                    execute_query.apply_async(args=[q.id], queue='llm_gemini')
            else:
                # No PENDING, find some failed ones and reset them
                print("No PENDING queries, resetting some FAILED queries...")
                result = await db.execute(
                    select(Query)
                    .where(Query.target_llm == 'gemini')
                    .where(Query.status == 'FAILED')
                    .order_by(Query.id.desc())
                    .limit(3)
                )
                queries = result.scalars().all()

                for q in queries:
                    q.status = 'PENDING'
                    q.error_message = None
                    print(f"  Reset query {q.id} to PENDING: {q.query_text[:50]}...")
                    execute_query.apply_async(args=[q.id], queue='llm_gemini')

                await db.commit()

    finally:
        await task_engine.dispose()

asyncio.run(main())
