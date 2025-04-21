
from time import sleep
from turtle import back
from celery import Celery

app = Celery('tasks', broker='redis://localhost:6379/0',backend='redis://localhost:6379/0')

@app.task
def generate_charts_asynchronously():
    #write code to generate charts
    pass
# import redis
# from celery_app import celery_app
# import uuid

# r = redis.Redis(host="localhost", port=6379, db=0)

# @celery_app.task
# def generate_charts_task(user_id: str):
#     # Simulate chart generation
#     charts = [f"chart_{uuid.uuid4()}" for _ in range(10)]
#     r.set(f"charts:next:{user_id}", str(charts))
#     return charts
