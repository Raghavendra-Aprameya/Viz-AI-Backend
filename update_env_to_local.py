"""Update .env file to use local PostgreSQL database."""
import os
import re

ENV_FILE = ".env"
LOCAL_DB_URI = "postgresql://vizai_user:vizai_password@localhost:5432/vizai_db"

def update_env_file():
    """Update DB_URI in .env file to point to local database."""
    if not os.path.exists(ENV_FILE):
        print(f"Error: {ENV_FILE} file not found!")
        return False
    
    # Read current .env file
    with open(ENV_FILE, 'r') as f:
        content = f.read()
    
    # Replace DB_URI line
    # Pattern to match DB_URI=... (with or without quotes)
    pattern = r'^DB_URI\s*=\s*.*$'
    replacement = f'DB_URI={LOCAL_DB_URI}'
    
    # Check if DB_URI exists
    if re.search(pattern, content, re.MULTILINE):
        # Replace existing DB_URI
        new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        print(f"✓ Updated existing DB_URI in {ENV_FILE}")
    else:
        # Append DB_URI if it doesn't exist
        new_content = content.rstrip() + f'\nDB_URI={LOCAL_DB_URI}\n'
        print(f"✓ Added DB_URI to {ENV_FILE}")
    
    # Write back to file
    with open(ENV_FILE, 'w') as f:
        f.write(new_content)
    
    print(f"\nUpdated {ENV_FILE} with local database connection:")
    print(f"  DB_URI={LOCAL_DB_URI}")
    return True

if __name__ == '__main__':
    if update_env_file():
        print("\n✓ Environment file updated successfully!")
        print("\nNext steps:")
        print("1. Restart your application")
        print("2. Test the connection to ensure everything works")
    else:
        print("\n✗ Failed to update environment file")

