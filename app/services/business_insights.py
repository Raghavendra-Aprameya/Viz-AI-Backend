"""
Business Insights Service Module

This module provides AI-powered business insights generation by:
1. Analyzing database schema to identify key business metrics
2. Using LangChain to generate KPI-focused SQL queries
3. Executing queries against the database
4. Using LLM to analyze results and generate insights

The service leverages LangChain for structured LLM interactions and
provides comprehensive business intelligence based on actual data.
"""

import json
import logging
from typing import Dict, List, Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
import google.generativeai as genai

from app.models.schema_models import (
    DatabaseConnectionModel,
    UserProjectRoleModel,
    UserModel,
)
from app.utils.crypt import decrypt_string
from app.core.settings import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def generate_business_insights_service(
    db: Session,
    token_payload: dict,
    database_connection_id: UUID,
) -> Dict[str, Any]:
    """
    Generate business insights by analyzing database schema and executing KPI queries.
    
    Workflow:
    1. Fetch database connection details
    2. Load pre-extracted schema from database (stored during connection creation)
    3. Use LangChain/LLM to identify KPIs and generate SQL queries
    4. Execute queries against the database
    5. Use LLM to analyze results and generate insights
    
    Args:
        db (Session): Database session
        token_payload (dict): User authentication token payload
        database_connection_id (UUID): ID of database connection to analyze
        
    Returns:
        dict: Business insights including KPIs, query results, and AI analysis
        
    Note:
        Gemini API key is loaded from environment variable GEMINI_API_KEY
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        
        # Fetch database connection
        db_connection = (
            db.query(DatabaseConnectionModel)
            .filter(DatabaseConnectionModel.id == database_connection_id)
            .first()
        )
        
        if not db_connection:
            raise HTTPException(
                status_code=404, 
                detail="Database connection not found"
            )
        
        # Verify user has access to this project
        user_role = (
            db.query(UserProjectRoleModel)
            .filter(
                UserProjectRoleModel.user_id == user_id,
                UserProjectRoleModel.project_id == db_connection.project_id,
            )
            .first()
        )
        
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        
        if not user_role and not user.is_super:
            raise HTTPException(
                status_code=403,
                detail="User does not have access to this project"
            )
        
        logger.info(f"Generating business insights for database: {db_connection.connection_name}")
        
        # Step 1: Get database schema from stored schema (already extracted during connection creation)
        if not db_connection.db_schema:
            raise HTTPException(
                status_code=400,
                detail="Database schema not found. Please reconnect the database."
            )
        
        try:
            schema_info = json.loads(db_connection.db_schema)
            logger.info(f"Loaded schema with {len(schema_info.get('tables', []))} tables")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse stored schema: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Invalid schema format in database connection"
            ) from e
        
        # Step 2: Use LLM to generate KPI queries
        # Ensure db_type has a default value
        db_type = db_connection.db_type or "postgres"
        
        kpi_queries = await generate_kpi_queries_with_llm(
            schema_info=schema_info,
            db_type=db_type,
        )
        
        # Step 3: Execute queries against database
        query_results = await execute_kpi_queries(
            db_connection=db_connection,
            queries=kpi_queries
        )
        
        # Step 4: Use LLM to analyze results and generate insights
        business_insights = await generate_insights_from_results(
            schema_info=schema_info,
            query_results=query_results,
        )
        
        return {
            "message": "Business insights generated successfully",
            "database_name": db_connection.connection_name,
            "database_type": db_connection.db_type or "postgres",
            "kpis_analyzed": len(kpi_queries),
            "kpi_queries": kpi_queries,
            "query_results": query_results,
            "insights": business_insights,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating business insights: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate business insights: {str(e)}"
        ) from e


async def extract_database_schema(db_connection: DatabaseConnectionModel) -> Dict[str, Any]:
    """
    Extract database schema information including tables, columns, and data types.
    
    NOTE: This is a fallback method. The primary method is to use the pre-extracted
    schema stored in db_connection.db_schema during connection creation.
    This function is kept for compatibility and schema refresh scenarios.
    
    Args:
        db_connection: Database connection model
        
    Returns:
        dict: Schema information with tables and columns
    """
    try:
        # Decrypt the connection string before using it
        decrypted_connection_string = decrypt_string(db_connection.db_connection_string)
        engine = create_engine(decrypted_connection_string)
        
        with engine.connect() as connection:
            # Get all tables
            if db_connection.db_type == "postgres":
                tables_query = text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    AND table_type = 'BASE TABLE'
                """)
            elif db_connection.db_type == "mysql":
                tables_query = text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = DATABASE()
                    AND table_type = 'BASE TABLE'
                """)
            else:
                tables_query = text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_type = 'BASE TABLE'
                """)
            
            result = connection.execute(tables_query)
            tables = [row[0] for row in result]
            
            # Get columns for each table
            schema_info = {"tables": []}
            
            for table in tables:
                if db_connection.db_type == "postgres":
                    columns_query = text(f"""
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_name = '{table}'
                        AND table_schema = 'public'
                        ORDER BY ordinal_position
                    """)
                elif db_connection.db_type == "mysql":
                    columns_query = text(f"""
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_name = '{table}'
                        AND table_schema = DATABASE()
                        ORDER BY ordinal_position
                    """)
                else:
                    columns_query = text(f"""
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_name = '{table}'
                        ORDER BY ordinal_position
                    """)
                
                col_result = connection.execute(columns_query)
                columns = [
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2]
                    }
                    for row in col_result
                ]
                
                schema_info["tables"].append({
                    "table_name": table,
                    "columns": columns
                })
        
        engine.dispose()
        return schema_info
        
    except Exception as e:
        logger.error(f"Error extracting database schema: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to extract database schema: {str(e)}"
        ) from e


async def generate_kpi_queries_with_llm(
    schema_info: Dict[str, Any],
    db_type: str,
) -> List[Dict[str, str]]:
    """
    Use LLM to analyze schema and generate 10 KPI-focused SQL queries.
    
    Args:
        schema_info: Database schema information
        db_type: Type of database (postgres, mysql, etc.)
        
    Returns:
        list: List of KPI queries with title, description, and SQL
        
    Note:
        Gemini API key is loaded from environment variable GEMINI_API_KEY
    """
    try:
        # Default to postgres if db_type is None
        if not db_type:
            db_type = "postgres"
            logger.warning("Database type not specified, defaulting to postgres")
        
        # Configure Gemini API from environment
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Create comprehensive prompt for KPI generation
        prompt = f"""
You are a business intelligence expert. Analyze the following database schema and generate 10 important KPI (Key Performance Indicator) SQL queries that would provide valuable business insights FOR THIS SPECIFIC DATABASE.

Database Type: {db_type}

Database Schema (USER'S BUSINESS DATA):
{json.dumps(schema_info, indent=2)}

IMPORTANT INSTRUCTIONS:
- This is a USER'S BUSINESS DATABASE, NOT a VizAI internal database
- DO NOT reference tables like "user", "project", "dashboard", "chart" unless they actually exist in the schema above
- ONLY use tables and columns that are explicitly listed in the schema above
- Generate queries relevant to THIS SPECIFIC business domain based on the table names and columns you see

For each KPI, provide:
1. A clear title for the KPI
2. A brief description of what business insight it provides
3. A valid {db_type.upper()} SQL query to calculate this KPI

Focus on KPIs based on the actual tables in the schema:
- If there are sales/transactions tables: revenue, growth, averages
- If there are customer tables: customer count, retention, acquisition
- If there are product tables: top products, inventory, performance
- If there are order tables: order volumes, fulfillment metrics
- Time-based trends using date/timestamp columns you find
- Distribution analysis across categories you find

Return the response as a JSON array with this exact structure:
[
  {{
    "kpi_title": "Total Revenue",
    "description": "Calculate the total revenue across all transactions",
    "sql_query": "SELECT SUM(amount) as total_revenue FROM sales"
  }},
  ...
]

CRITICAL REQUIREMENTS:
- Generate exactly 10 KPIs
- Use ONLY tables and columns from the schema provided above
- Queries must be syntactically correct for {db_type} (use {db_type}-specific syntax)
- For PostgreSQL: Use INTERVAL '30 days', DATE_TRUNC, etc.
- For MySQL: Use DATE_SUB, DATE_FORMAT, etc.
- Use appropriate aggregations (SUM, COUNT, AVG, MAX, MIN)
- Include GROUP BY where necessary
- Use meaningful aliases for all calculated fields
- Ensure all column references exist in the schema

Return ONLY the JSON array, no additional text or markdown.
DO NOT include explanations, self-corrections, or any other text.
DO NOT include markdown code fences.
Just the raw JSON array starting with [ and ending with ].
"""
        
        logger.info("Generating KPI queries with LLM...")
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
        
        # Try to extract JSON array if there's extra text
        # Look for the JSON array pattern
        if response_text.startswith("[") and "]" in response_text:
            # Find the closing bracket of the JSON array
            bracket_count = 0
            json_end = 0
            for i, char in enumerate(response_text):
                if char == "[":
                    bracket_count += 1
                elif char == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        json_end = i + 1
                        break
            if json_end > 0:
                response_text = response_text[:json_end]
        
        kpi_queries = json.loads(response_text)
        
        logger.info(f"Generated {len(kpi_queries)} KPI queries")
        return kpi_queries
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {str(e)}")
        logger.error(f"Response text (first 500 chars): {response_text[:500]}")
        raise HTTPException(
            status_code=500,
            detail="Failed to parse KPI queries from LLM response"
        ) from e
    except Exception as e:
        logger.error(f"Error generating KPI queries: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate KPI queries: {str(e)}"
        ) from e


async def execute_kpi_queries(
    db_connection: DatabaseConnectionModel,
    queries: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """
    Execute all KPI queries against the database and collect results.
    
    Args:
        db_connection: Database connection model
        queries: List of KPI queries to execute
        
    Returns:
        list: Query results with KPI data
    """
    try:
        # Decrypt the connection string before using it
        decrypted_connection_string = decrypt_string(db_connection.db_connection_string)
        engine = create_engine(decrypted_connection_string)
        results = []
        
        for kpi in queries:
            # Use a new connection for each query to avoid transaction issues
            try:
                with engine.connect() as connection:
                    logger.info(f"Executing query for KPI: {kpi['kpi_title']}")
                    
                    query_result = connection.execute(text(kpi['sql_query']))
                    
                    # Convert results to list of dictionaries
                    columns = query_result.keys()
                    rows = [dict(zip(columns, row)) for row in query_result.fetchall()]
                    
                    # Convert any non-serializable types
                    serializable_rows = []
                    for row in rows:
                        serializable_row = {}
                        for key, value in row.items():
                            if value is None:
                                serializable_row[key] = None
                            elif isinstance(value, (int, float, str, bool)):
                                serializable_row[key] = value
                            else:
                                serializable_row[key] = str(value)
                        serializable_rows.append(serializable_row)
                    
                    results.append({
                        "kpi_title": kpi['kpi_title'],
                        "description": kpi['description'],
                        "query": kpi['sql_query'],
                        "success": True,
                        "data": serializable_rows,
                        "row_count": len(serializable_rows)
                    })
                    
            except Exception as query_error:
                logger.error(f"Error executing query for {kpi['kpi_title']}: {str(query_error)}")
                results.append({
                    "kpi_title": kpi['kpi_title'],
                    "description": kpi['description'],
                    "query": kpi['sql_query'],
                    "success": False,
                    "error": str(query_error),
                    "data": [],
                    "row_count": 0
                })
        
        engine.dispose()
        
        successful_queries = sum(1 for r in results if r['success'])
        logger.info(f"Executed {successful_queries}/{len(queries)} queries successfully")
        
        return results
        
    except Exception as e:
        logger.error(f"Error executing KPI queries: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute KPI queries: {str(e)}"
        ) from e


async def generate_insights_from_results(
    schema_info: Dict[str, Any],
    query_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Use LLM to analyze query results and generate business insights.
    
    Args:
        schema_info: Database schema information
        query_results: Results from executed KPI queries
        
    Returns:
        dict: Business insights and recommendations
        
    Note:
        Gemini API key is loaded from environment variable GEMINI_API_KEY
    """
    try:
        # Configure Gemini API from environment
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Prepare query results summary
        results_summary = []
        for result in query_results:
            if result['success']:
                results_summary.append({
                    "kpi": result['kpi_title'],
                    "description": result['description'],
                    "data": result['data'][:5]  # Limit to first 5 rows for context
                })
        
        # Create prompt for insight generation
        prompt = f"""
You are a business analyst. Analyze the following KPI query results and provide comprehensive business insights.

KPI Results:
{json.dumps(results_summary, indent=2)}

Provide a detailed analysis including:

1. **Executive Summary**: A brief overview of the key findings (2-3 sentences)

2. **Key Metrics Analysis**: For each major KPI, explain:
   - What the numbers mean
   - Whether they indicate positive or negative trends
   - Potential business implications

3. **Insights & Patterns**: Identify:
   - Notable trends or patterns
   - Anomalies or unexpected results
   - Correlations between different metrics

4. **Recommendations**: Provide 3-5 actionable recommendations based on the data

5. **Areas of Concern**: Highlight any metrics that require immediate attention

Return the response as a JSON object with this structure:
{{
  "executive_summary": "string",
  "key_metrics": [
    {{
      "kpi_name": "string",
      "value_interpretation": "string",
      "business_impact": "string"
    }}
  ],
  "insights_and_patterns": [
    "string"
  ],
  "recommendations": [
    {{
      "priority": "high|medium|low",
      "title": "string",
      "description": "string"
    }}
  ],
  "areas_of_concern": [
    "string"
  ]
}}

Be specific, data-driven, and actionable in your analysis.

Return ONLY the JSON object, no additional text.
DO NOT include explanations, self-corrections, thinking process, or any other text.
DO NOT include markdown code fences.
Just the raw JSON object starting with {{ and ending with }}.
"""
        
        logger.info("Generating business insights with LLM...")
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
        
        # Try to extract JSON object if there's extra text
        # Look for the JSON object pattern
        if response_text.startswith("{") and "}" in response_text:
            # Find the closing brace of the JSON object
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
        
        insights = json.loads(response_text)
        
        logger.info("Business insights generated successfully")
        return insights
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse insights response as JSON: {str(e)}")
        logger.error(f"Response text (first 1000 chars): {response_text[:1000]}")
        raise HTTPException(
            status_code=500,
            detail="Failed to parse business insights from LLM response"
        ) from e
    except Exception as e:
        logger.error(f"Error generating business insights: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate business insights: {str(e)}"
        ) from e

