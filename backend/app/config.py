"""All settings come from environment variables so nothing secret lives in the code."""
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://desk:desk@localhost:5432/desk")

# In docker-compose this is set from the .env file. The fallback is only for local dev.
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
JWT_ALGORITHM = "HS256"
TOKEN_MINUTES = int(os.getenv("TOKEN_MINUTES", "480"))  # one working day

# bcrypt work factor. 12 is a good production value; tests lower it to run fast.
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
