"""
This module migrates the database by creating the tables defined in the schema_models module.
"""

from app.core.db import engine
from app.models.schema_models import Base
from app.models.knowledge_graph_models import DocumentKnowledgeGraphModel

Base.metadata.create_all(engine)
print("✅ Tables created successfully!")
