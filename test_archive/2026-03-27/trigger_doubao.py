#!/usr/bin/env python3
"""Trigger Doubao queries"""
import sys
import os
os.environ['PYTHONPATH'] = '/app'

from geo_tracker.tasks.celery_tasks import execute_query

print("Looking for Doubao queries...")

# First let's check the DB directly
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = "postgresql://genpano:genpano2026@localhost:5432/genpano"
import re
match = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", DATABASE_URL)
if match:
    DB_USER = match.group(1)
    DB_PASS = match.group(2)
    DB_HOST = match.group(3)
    DB_PORT = match.group(4)
    DB_NAME = match.group(5)

# But we're on local, let's just make a script to run on server
script_content = '''
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
                .where(Query.target_llm == 'doubao')
                .where(Query.status == 'PENDING')
                .order_by(Query.id)
                .limit(10)
            )
            queries = result.scalars().all()

            print(f"Found {len(queries)} Doubao queries")
            for q in queries:
                print(f"  Triggering query {q.id}: {q.query_text[:50]}...")
                execute_query.apply_async(args=[q.id], queue='llm_doubao')

            if not queries:
                print("No PENDING Doubao queries found, looking for any Doubao queries...")
                result = await db.execute(
                    select(Query)
                    .where(Query.target_llm == 'doubao')
                    .order_by(Query.id.desc())
                    .limit(10)
                )
                queries = result.scalars().all()
                if queries:
                    print(f"Found {len(queries)} existing Doubao queries:")
                    for q in queries:
                        print(f"  [{q.id}] {q.status}: {q.query_text[:50]}...")

    finally:
        await task_engine.dispose()

asyncio.run(main())
'''

with open('trigger_doubao_remote.py', 'w', encoding='utf-8') as f:
    f.write(script_content)

print("Created trigger_doubao_remote.py")
