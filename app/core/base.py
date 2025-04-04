from sqlalchemy.orm import declarative_base

Base = declarative_base()
import app.models.schema_models  # <-- this line is key!

