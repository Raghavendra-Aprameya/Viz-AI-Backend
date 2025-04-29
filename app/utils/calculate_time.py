# # app/utils/calculate_time.py
# from fastapi import Request, Depends
# from sqlalchemy.orm import Session
# import time
# from typing import Callable
# from app.core.db import get_db
# from app.models.schema_models import ResponseTimeModel

# async def track_and_store_time(request: Request, db: Session = Depends(get_db)):
#     # Store the start time in the request state
#     request.state.start_time = time.time()
    
#     # This will be called after the request is processed
#     async def store_time_in_db():
#         process_time = time.time() - request.state.start_time
#         path = request.url.path
        
#         try:
#             # Check if there's an existing record for this path
#             existing_record = db.query(ResponseTimeModel).filter(
#                 ResponseTimeModel.url == path
#             ).first()
            
#             if existing_record:
#                 # Update the average time
#                 new_avg = ((existing_record.avg_process_time * existing_record.request_count) + process_time) / (existing_record.request_count + 1)
#                 existing_record.avg_process_time = new_avg
#                 existing_record.request_count += 1
#                 existing_record.last_process_time = process_time
#             else:
#                 # Create new record
#                 new_record = ResponseTimeModel(
#                     url=path,
#                     avg_process_time=process_time,
#                     last_process_time=process_time,
#                     request_count=1
#                 )
#                 db.add(new_record)
                
#             db.commit()
#             print(f"Request URL: {path}, Processing Time: {process_time:.4f} seconds")
            
#         except Exception as e:
#             db.rollback()
#             print(f"Failed to store response time: {e}")
    
#     # Add the callback to be executed after the request
#     request.scope["app"].middleware_stack.add_task(store_time_in_db)