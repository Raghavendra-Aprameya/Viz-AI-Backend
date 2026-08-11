import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.db import SessionLocal
from app.models.schema_models import UserModel
from app.utils.crypt import get_password_hash

def create_super_admin():
    db = SessionLocal()
    try:
        # Check if user already exists
        existing_user = db.query(UserModel).filter_by(username="another_super_admin").first()
        if existing_user:
            print("User 'another_super_admin' already exists.")
            return

        new_user = UserModel(
            username="another_super_admin",
            email="another_super_admin@vizai.com",
            password=get_password_hash("password"), # password set to "password"
            is_super=True
        )
        db.add(new_user)
        db.commit()
        print("✅ Successfully created 'another_super_admin' with password 'password'!")
        print("✅ Successfully created 'another_super_admin' with password 'password'!")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_super_admin()
