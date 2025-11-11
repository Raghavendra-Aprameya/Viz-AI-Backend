"""
Project-Wide Business Insights Service Module

This module generates comprehensive business insights across ALL database connections
within a project, providing a unified strategic view of the entire project's data.
"""

import json
import logging
from typing import Dict, List, Any
from uuid import UUID

import redis
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import google.generativeai as genai

from app.models.schema_models import (
    DatabaseConnectionModel,
    UserProjectRoleModel,
    UserModel,
    ProjectModel,
)
from app.core.settings import settings

from app.services.business_insights import (
    generate_kpi_queries_with_llm,
    execute_kpi_queries,
    generate_insights_from_results,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

REDIS_TTL_SECONDS = 3600  # 1 hour
REDIS_PREFIX = "project_business_insights"
redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)


def _make_cache_key(project_id: UUID) -> str:
    """Construct Redis cache key for project-level insights."""
    return f"{REDIS_PREFIX}:{str(project_id)}"


def _serialize_for_cache(payload: Dict[str, Any]) -> str:
    """Serialize payload into JSON, coercing non-JSON types to string."""

    def default_serializer(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    return json.dumps(payload, default=default_serializer)


async def generate_project_insights_service(
    db: Session,
    token_payload: dict,
    project_id: UUID,
) -> Dict[str, Any]:
    """
    Generate comprehensive business insights for ALL database connections within a project.
    
    This function:
    1. Fetches all database connections for the project
    2. Generates insights for each database connection (10 KPIs each)
    3. Aggregates insights across all databases
    4. Uses LLM to create a unified project-level business analysis
    
    Args:
        db (Session): Database session
        token_payload (dict): User authentication token payload
        project_id (UUID): ID of project to analyze
        
    Returns:
        dict: Comprehensive project-level business insights
        
    Note:
        Gemini API key is loaded from environment variable GEMINI_API_KEY
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        
        # Verify project exists
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found"
            )
        
        # Verify user has access to this project
        user_role = (
            db.query(UserProjectRoleModel)
            .filter(
                UserProjectRoleModel.user_id == user_id,
                UserProjectRoleModel.project_id == project_id,
            )
            .first()
        )
        
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        
        if not user_role and not user.is_super:
            raise HTTPException(
                status_code=403,
                detail="User does not have access to this project"
            )
        
        cache_key = _make_cache_key(project_id)
        try:
            cached_insights = redis_client.get(cache_key)
            if cached_insights:
                logger.info(
                    "Returning cached project business insights for project %s",
                    project_id,
                )
                return json.loads(cached_insights)
        except redis.RedisError as redis_err:
            logger.warning(
                "Redis unavailable while fetching project insights cache: %s", redis_err
            )

        logger.info(f"Generating project-wide insights for project: {project.name}")
        
        # Get all database connections for this project
        db_connections = (
            db.query(DatabaseConnectionModel)
            .filter(DatabaseConnectionModel.project_id == project_id)
            .all()
        )
        
        if not db_connections:
            raise HTTPException(
                status_code=404,
                detail="No database connections found for this project"
            )
        
        logger.info(f"Found {len(db_connections)} database connections")
        
        # Generate insights for each database
        all_database_insights = []
        
        for db_connection in db_connections:
            try:
                logger.info(f"Analyzing database: {db_connection.connection_name}")
                
                # Load schema
                if not db_connection.db_schema:
                    logger.warning(f"Skipping {db_connection.connection_name} - no schema available")
                    all_database_insights.append({
                        "database_id": str(db_connection.id),
                        "database_name": db_connection.connection_name,
                        "database_type": db_connection.db_type or "unknown",
                        "status": "skipped",
                        "error": "No schema available",
                        "insights": None
                    })
                    continue
                
                schema_info = json.loads(db_connection.db_schema)
                db_type = db_connection.db_type or "postgres"
                
                # Generate KPI queries
                kpi_queries = await generate_kpi_queries_with_llm(
                    schema_info=schema_info,
                    db_type=db_type,
                )
                
                # Execute queries
                query_results = await execute_kpi_queries(
                    db_connection=db_connection,
                    queries=kpi_queries
                )
                
                # Generate insights
                database_insights = await generate_insights_from_results(
                    schema_info=schema_info,
                    query_results=query_results,
                )
                
                all_database_insights.append({
                    "database_id": str(db_connection.id),
                    "database_name": db_connection.connection_name,
                    "database_type": db_type,
                    "kpis_analyzed": len(kpi_queries),
                    "successful_queries": sum(1 for r in query_results if r['success']),
                    "status": "success",
                    "insights": database_insights
                })
                
            except Exception as e:
                logger.error(f"Error analyzing {db_connection.connection_name}: {str(e)}")
                all_database_insights.append({
                    "database_id": str(db_connection.id),
                    "database_name": db_connection.connection_name,
                    "database_type": db_connection.db_type or "unknown",
                    "status": "failed",
                    "error": str(e),
                    "insights": None
                })
        
        # Generate consolidated project-level insights
        consolidated_insights = await generate_consolidated_insights(
            project_name=project.name,
            database_insights=all_database_insights,
        )
        
        result = {
            "message": "Project-wide business insights generated successfully",
            "project_id": str(project_id),
            "project_name": project.name,
            "total_databases_analyzed": len(db_connections),
            "successful_analyses": sum(1 for d in all_database_insights if d.get('status') == 'success'),
            "database_insights": all_database_insights,
            "consolidated_insights": consolidated_insights
        }

        try:
            redis_client.setex(cache_key, REDIS_TTL_SECONDS, _serialize_for_cache(result))
            logger.info(
                "Stored project business insights in cache for project %s with TTL %s seconds",
                project_id,
                REDIS_TTL_SECONDS,
            )
        except redis.RedisError as redis_err:
            logger.warning(
                "Failed to cache project business insights for project %s: %s",
                project_id,
                redis_err,
            )

        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating project insights: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate project insights: {str(e)}"
        ) from e


async def generate_consolidated_insights(
    project_name: str,
    database_insights: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Generate consolidated business insights across all databases in a project.
    
    Args:
        project_name: Name of the project
        database_insights: List of insights from each database
        
    Returns:
        dict: Consolidated project-level insights
        
    Note:
        Gemini API key is loaded from environment variable GEMINI_API_KEY
    """
    try:
        # Configure Gemini API from environment
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Prepare summary of all database insights
        databases_summary = []
        for db_insight in database_insights:
            if db_insight.get('insights'):
                databases_summary.append({
                    "database_name": db_insight['database_name'],
                    "database_type": db_insight['database_type'],
                    "executive_summary": db_insight['insights'].get('executive_summary'),
                    "top_recommendations": db_insight['insights'].get('recommendations', [])[:3],
                    "areas_of_concern": db_insight['insights'].get('areas_of_concern', [])[:3]
                })
        
        prompt = f"""
You are a senior business strategist. Analyze insights from multiple data sources for the project "{project_name}" and provide a unified strategic overview.

Insights from {len(databases_summary)} Databases:
{json.dumps(databases_summary, indent=2)}

Provide a consolidated strategic analysis including:

1. **Overall Business Health**: High-level assessment across all data sources (1-2 sentences)
2. **Cross-Database Patterns**: Identify patterns or correlations across different databases with reasoning
3. **Strategic Priorities**: Top 5 strategic priorities based on all insights with reasoning
4. **Risk Assessment**: Key risks identified across all data sources with reasoning
5. **Opportunities**: Growth and optimization opportunities with reasoning

Return the response as a JSON object with this structure:
{{
  "overall_health_score": "excellent|good|fair|poor",
  "health_assessment": "string",
  "reasoning": "string (explain your analytical approach and key cross-database insights that informed this assessment)",
  "cross_database_patterns": [
    {{
      "pattern": "string",
      "reasoning": "string (explain what data from which databases led to identifying this pattern)"
    }}
  ],
  "strategic_priorities": [
    {{
      "rank": 1,
      "title": "string",
      "description": "string",
      "impact": "high|medium|low",
      "reasoning": "string (explain which insights from which databases justify this priority)"
    }}
  ],
  "risk_assessment": {{
    "critical_risks": [
      {{
        "risk": "string",
        "reasoning": "string (explain what data points across databases indicate this risk)"
      }}
    ],
    "moderate_risks": [
      {{
        "risk": "string",
        "reasoning": "string (explain what data points indicate this risk)"
      }}
    ]
  }},
  "opportunities": [
    {{
      "title": "string",
      "description": "string",
      "potential_impact": "string",
      "reasoning": "string (explain which metrics or patterns suggest this opportunity)"
    }}
  ]
}}

Be strategic, data-driven, and actionable.

Return ONLY the JSON object, no additional text.
DO NOT include explanations, self-corrections, thinking process, or any other text.
DO NOT include markdown code fences.
Just the raw JSON object starting with {{ and ending with }}.
"""
        
        logger.info("Generating consolidated project insights...")
        response = model.generate_content(prompt)
        
        # Parse JSON response
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text.split("```json")[1]
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
        if "```" in response_text:
            response_text = response_text.split("```")[0]
        
        response_text = response_text.strip()
        
        # Extract JSON object
        if response_text.startswith("{") and "}" in response_text:
            brace_count = 0
            json_end = 0
            for i, char in enumerate(response_text):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
            if json_end > 0:
                response_text = response_text[:json_end]
        
        consolidated = json.loads(response_text)
        
        logger.info("Consolidated project insights generated successfully")
        return consolidated
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse consolidated insights: {str(e)}")
        logger.error(f"Response text (first 1000 chars): {response_text[:1000] if 'response_text' in locals() else 'N/A'}")
        # Return fallback structure
        return {
            "overall_health_score": "unknown",
            "health_assessment": "Unable to generate consolidated insights",
            "reasoning": "Failed to parse LLM response",
            "cross_database_patterns": [],
            "strategic_priorities": [],
            "risk_assessment": {
                "critical_risks": [],
                "moderate_risks": []
            },
            "opportunities": []
        }
    except Exception as e:
        logger.error(f"Error generating consolidated insights: {str(e)}")
        # Return fallback structure
        return {
            "overall_health_score": "unknown",
            "health_assessment": f"Error: {str(e)}",
            "reasoning": f"Error generating insights: {str(e)}",
            "cross_database_patterns": [],
            "strategic_priorities": [],
            "risk_assessment": {
                "critical_risks": [],
                "moderate_risks": []
            },
            "opportunities": []
        }

