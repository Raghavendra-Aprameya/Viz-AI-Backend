
# LOCK_EXPIRY_SECONDS = 300  # 5 minutes
# WAIT_TIMEOUT_SECONDS = 20 # 10 seconds max wait
# WAIT_POLL_INTERVAL_SECONDS = 1  # 1 second polling

# async def generate_charts_service(
#     request: QueryRequest,
#     project_id: UUID,
#     datasource_connection_id: UUID = None,
#     db: Session = Depends(get_db),
#     token_payload: dict = Depends(get_current_user),
# ):
#     try:
#         user_id = UUID(token_payload.get("sub"))

#         redis_current_key = f"charts:current:{user_id}"
#         redis_next_key = f"charts:next:{user_id}"
#         redis_generating_key = f"charts:generating:{user_id}"

#         # Step 0: Delete existing current charts
#         r.delete(redis_current_key)

#         # Step 1: Check if "next" charts exist
#         next_charts_json = r.get(redis_next_key)
#         if next_charts_json:
#             logger.info(f"[{user_id}] Found next charts, using them as current.")

#             r.set(redis_current_key, next_charts_json, ex=3600)
#             r.delete(redis_next_key)

#             return {
#                 "status": "success",
#                 "message": "Charts retrieved from pre-generated next cache",
#                 "charts": json.loads(next_charts_json),
#                 "source": "next"
#             }

#         # Step 2: If no next charts, check if worker is generating
#         generating = r.get(redis_generating_key)
#         if generating:
#             logger.info(f"[{user_id}] Worker is generating, waiting up to {WAIT_TIMEOUT_SECONDS}s...")

#             for _ in range(WAIT_TIMEOUT_SECONDS):
#                 await asyncio.sleep(WAIT_POLL_INTERVAL_SECONDS)

#                 next_charts_json = r.get(redis_next_key)
#                 if next_charts_json:
#                     logger.info(f"[{user_id}] Worker finished during wait. Using new charts.")

#                     r.set(redis_current_key, next_charts_json, ex=3600)
#                     r.delete(redis_next_key)

#                     return {
#                         "status": "success",
#                         "message": "Charts retrieved after waiting for worker",
#                         "charts": json.loads(next_charts_json),
#                         "source": "waited"
#                     }

#             logger.warning(f"[{user_id}] Timeout while waiting for worker.")

#         # Step 3: No next charts, no generating worker => Server generates charts now
#         logger.info(f"[{user_id}] No pre-generated charts available. Generating now on server.")

#         chart_models = await generate_and_store_charts(
#             db=db,
#             datasource_connection_id=datasource_connection_id,
#             project_id=project_id,
#             query_request=request,
#             token_payload=token_payload
#         )

#         charts_serialized = [{
#             "id": str(chart.id),
#             "title": chart.title,
#             "chart_type": chart.chart_type,
#             "created_at": chart.created_at.isoformat() if hasattr(chart, 'created_at') else None,
#             "data": chart.data if hasattr(chart, 'data') else None,
#         } for chart in chart_models]

#         r.set(redis_current_key, json.dumps(charts_serialized), ex=3600)

#         # Also trigger background worker to pre-generate next batch
#         trigger_async_worker(user_id, project_id, datasource_connection_id, request)

#         return {
#             "status": "success",
#             "message": "Charts generated freshly by server",
#             "charts": charts_serialized,
#             "source": "fresh"
#         }

#     except Exception as e:
#         logger.error(f"Error in generate_charts_service: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Failed to generate charts: {str(e)}"
#         )
# async def refresh_service(
#     request: QueryRequest,
#     project_id: UUID,
#     datasource_connection_id: UUID = None,
#     db: Session = Depends(get_db),
#     token_payload: dict = Depends(get_current_user),
# ):
#     pass

# def trigger_async_worker(user_id, project_id, datasource_connection_id, request):
#     """
#     Helper to safely trigger async chart generation with Redis lock.
#     """
#     redis_generating_key = f"charts:generating:{user_id}"

#     lock_acquired = r.set(redis_generating_key, "1", nx=True, ex=LOCK_EXPIRY_SECONDS)

#     if not lock_acquired:
#         logger.info(f"[{user_id}] Async worker already running, no need to trigger.")
#         return

#     generate_charts_asynchronously.delay(
#         user_id=str(user_id),
#         datasource_connection_id=str(datasource_connection_id) if datasource_connection_id else None,
#         project_id=str(project_id),
#         query_request=request.dict()
#     )

#     logger.info(f"[{user_id}] Triggered async worker for next chart generation.")




# @backend_router.post("/generate-charts/{project_id}/{datasource_connection_id}")
# async def generate_charts(
#     request: QueryRequest,
#     project_id: UUID = Path(..., description="Project ID to generate charts for"),
#     datasource_connection_id: UUID = Path(..., description="Datasource connection ID to generate charts for"),
#     db: Session = Depends(get_db),
#     token_payload: dict = Depends(get_current_user)
# ):
#     """
#     API endpoint to generate charts for a specific project and datasource connection.
    
#     Args:
#         request (QueryRequest): Query parameters for chart generation
#         project_id (UUID): ID of the project
#         datasource_connection_id (UUID): ID of the datasource connection
#         db (Session): Database session
#         token_payload (dict): User authentication token payload
        
#     Returns:
#         dict: Generated charts data and status information
#     """
#     return await generate_charts_service(
#         request,
#         project_id,
#         datasource_connection_id,
#         db,
#         token_payload
#     )
# @backend_router.post("/refresh-charts/{project_id}/{datasource_connection_id}", status_code=status.HTTP_200_OK)
# async def refresh_charts(
#     request: QueryRequest,
#     project_id: UUID = Path(..., description="Project ID to generate charts for"),
#     datasource_connection_id: UUID = Path(..., description="Datasource connection ID to generate charts for"),
#     db: Session = Depends(get_db),
#     token_payload: dict = Depends(get_current_user)
# ):
#     """
#     Endpoint to refresh charts using pre-generated charts from Redis.
    
#     This endpoint:
#     1. Retrieves pre-generated charts from Redis
#     2. Sets them as the current charts
#     3. Triggers asynchronous generation of the next batch
    
#     Args:
#         db (Session): The database session
#         token_payload (dict): The token payload
#         datasource_connection_id (UUID): ID of the datasource connection
#         project_id (UUID): ID of the project
        
#     Returns:
#         dict: Refreshed charts data and status information
#     """
#     return await refresh_service(
#         request,
#         project_id=project_id,
#         datasource_connection_id=datasource_connection_id,
#         db=db,
#         token_payload=token_payload
#     )
