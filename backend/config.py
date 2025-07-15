import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Neo4j Configuration
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "password"
    
    # OpenAI Configuration
    openai_api_key: Optional[str] = None
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    
    # Application Configuration
    environment: str = "development"
    log_level: str = "INFO"
    
    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        extra = 'forbid'  # Prevent extra fields that don't match the model

settings = Settings() 