
from app.utils.tasks import generate_charts_asynchronously

async def generate_charts_service():

   
        #write code to generate first set of charts
        #r.set('charts', charts)
        # generate_charts_asynchronously.delay()
        #return first set of charts
        pass
async def refresh_service():
    #write code to replace old charts wirh new charts
    #rerun generate_charts_asynchronously.delay()
    # return new charts
    pass


# from fastapi import FastAPI
# from tasks import generate_charts_task
# import redis
# import uuid

# app = FastAPI()
# r = redis.Redis(host="localhost", port=6379, db=0)

# @app.get("/test")
# def test_generate(user_id: str = "demo_user"):
#     # Generate current charts
#     current_charts = [f"chart_{uuid.uuid4()}" for _ in range(10)]
#     r.set(f"charts:current:{user_id}", str(current_charts))

#     # Start background job for next batch
#     generate_charts_task.delay(user_id)

#     return {"charts": current_charts}

# @app.get("/refresh")
# def refresh_charts(user_id: str = "demo_user"):
#     # Replace old charts with pre-generated
#     next_charts = r.get(f"charts:next:{user_id}")
#     if next_charts:
#         r.set(f"charts:current:{user_id}", next_charts)
#         # Kick off next round
#         generate_charts_task.delay(user_id)
#         return {"refreshed_charts": next_charts.decode("utf-8")}
#     else:
#         return {"error": "No new charts generated yet"}
