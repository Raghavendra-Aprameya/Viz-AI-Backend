"""
Service layer for managing home insights.

This module provides functions to save and retrieve insights that users
want to pin to their home page for quick access.
"""

from uuid import UUID
from datetime import datetime
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import desc
from fastapi import HTTPException, status

from app.models.schema_models import HomeInsightModel, UserModel, ProjectModel


async def save_home_insight_service(
    data: dict,
    db: Session,
    token_payload: dict
) -> dict:
    """
    Save an insight to the user's home page.
    
    Args:
        data: Insight data containing title, description, type, etc.
        db: Database session
        token_payload: JWT token payload containing user information
        
    Returns:
        dict: Response containing the saved insight details
        
    Raises:
        HTTPException: If user is not authenticated or project doesn't exist
    """
    # Get user ID from token
    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated"
        )
    
    user_id = UUID(user_id_str)
    
    # Verify user exists
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify project exists
    project = db.query(ProjectModel).filter(
        ProjectModel.id == data["project_id"]
    ).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Create new home insight
    home_insight = HomeInsightModel(
        user_id=user_id,
        project_id=data["project_id"],
        title=data["title"],
        description=data["description"],
        insight_type=data["insight_type"],
        category=data["category"],
        impact=data["impact"],
        source=data.get("source")
    )
    
    db.add(home_insight)
    db.commit()
    db.refresh(home_insight)
    
    return {
        "message": "Insight saved to home successfully",
        "insight": {
            "id": str(home_insight.id),
            "user_id": str(home_insight.user_id),
            "project_id": str(home_insight.project_id),
            "title": home_insight.title,
            "description": home_insight.description,
            "insight_type": home_insight.insight_type,
            "category": home_insight.category,
            "impact": home_insight.impact,
            "source": home_insight.source,
            "created_at": home_insight.created_at.isoformat()
        }
    }


async def get_home_insights_service(
    db: Session,
    token_payload: dict,
    project_id: UUID = None,
    limit: int = 10
) -> dict:
    """
    Get all home insights for the current user.
    
    Args:
        db: Database session
        token_payload: JWT token payload containing user information
        project_id: Optional project ID to filter insights
        limit: Maximum number of insights to return
        
    Returns:
        dict: Response containing list of insights and total count
        
    Raises:
        HTTPException: If user is not authenticated
    """
    # Get user ID from token
    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated"
        )
    
    user_id = UUID(user_id_str)
    
    # Build query
    query = db.query(HomeInsightModel).filter(
        HomeInsightModel.user_id == user_id
    )
    
    # Filter by project if specified
    if project_id:
        query = query.filter(HomeInsightModel.project_id == project_id)
    
    # Order by most recent first and apply limit
    insights = query.order_by(desc(HomeInsightModel.created_at)).limit(limit).all()
    
    # Get total count (without limit)
    total_count = db.query(HomeInsightModel).filter(
        HomeInsightModel.user_id == user_id
    ).count()
    
    # Format response
    insights_data = [
        {
            "id": str(insight.id),
            "user_id": str(insight.user_id),
            "project_id": str(insight.project_id),
            "title": insight.title,
            "description": insight.description,
            "insight_type": insight.insight_type,
            "category": insight.category,
            "impact": insight.impact,
            "source": insight.source,
            "created_at": insight.created_at.isoformat()
        }
        for insight in insights
    ]
    
    return {
        "message": "Home insights retrieved successfully",
        "insights": insights_data,
        "total_count": total_count
    }


async def delete_home_insight_service(
    insight_id: UUID,
    db: Session,
    token_payload: dict
) -> dict:
    """
    Delete a home insight.
    
    Args:
        insight_id: ID of the insight to delete
        db: Database session
        token_payload: JWT token payload containing user information
        
    Returns:
        dict: Response confirming deletion
        
    Raises:
        HTTPException: If user is not authenticated or insight not found
    """
    # Get user ID from token
    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated"
        )
    
    user_id = UUID(user_id_str)
    
    # Find insight
    insight = db.query(HomeInsightModel).filter(
        HomeInsightModel.id == insight_id,
        HomeInsightModel.user_id == user_id
    ).first()
    
    if not insight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insight not found or you don't have permission to delete it"
        )
    
    db.delete(insight)
    db.commit()
    
    return {
        "message": "Insight removed from home successfully"
    }

