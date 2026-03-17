import psycopg2

try:
    conn = psycopg2.connect(
        host="rtb-dev-db.c4b40c4s2ytd.us-east-1.rds.amazonaws.com",
        port=5432,
        database="rtb",
        user="rtbadmin",
        password="rtb-dev-2025-pixid"
    )

    cursor = conn.cursor()

    # Test query
    cursor.execute("SELECT version();")
    db_version = cursor.fetchone()
    print("Connected to:", db_version)

    cursor.close()
    conn.close()

except Exception as e:
    print("Error:", e)