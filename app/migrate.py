from app.core.db import engine
from app.models.schema_models import Base

Base.metadata.create_all(engine)
print("✅ Tables created successfully!")
