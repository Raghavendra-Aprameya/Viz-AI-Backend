# VizAI Backend Environment Configuration

## 📋 Required Environment Variables

Add these to your `.env` file in the `Viz-AI-Backend/` directory:

```bash
# Database Configuration
DB_URI=postgresql://username:password@localhost/vizai_db

# JWT Configuration
SECRET_KEY=your-jwt-secret-key-here
REFRESH_SECRET_KEY=your-refresh-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
REFRESH_TOKEN_EXPIRE_DAYS=7

# Encryption (for database connection strings and passwords)
ENCRYPTION_KEY=your-fernet-encryption-key-here

# Google Gemini API (Required for Business Insights Feature)
GEMINI_API_KEY=your-gemini-api-key-here
```

---

## 🔑 Getting Your Gemini API Key

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key
5. Add to your `.env` file:
   ```bash
   GEMINI_API_KEY=AIzaSyD17MVZM5tlI6TZ41pVOR7v249T9Xoj58Y
   ```

---

## 🔐 Generating Encryption Key

To generate a valid Fernet encryption key:

```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()
print(key.decode())
```

Add the output to your `.env` file.

---

## ✅ Verification

After setting up your `.env` file, verify the configuration:

```bash
# Start the backend
cd Viz-AI-Backend
source venv/bin/activate
uvicorn app.main:app --reload
```

Check the startup logs for any missing environment variable errors.

---

## 🚀 Features Requiring Environment Variables

| Feature | Required Env Var |
|---------|------------------|
| **User Authentication** | `SECRET_KEY`, `REFRESH_SECRET_KEY` |
| **Database Connection** | `DB_URI`, `ENCRYPTION_KEY` |
| **Business Insights** | `GEMINI_API_KEY` |
| **Chart Generation (AI)** | `GEMINI_API_KEY` |
| **NL2SQL** | `GEMINI_API_KEY` |

---

## 📝 Notes

- **Never commit your `.env` file** to version control
- API keys are sensitive - keep them secure
- Rotate API keys periodically for security
- Use different keys for development and production
- Consider using secret management tools (AWS Secrets Manager, HashiCorp Vault) for production

