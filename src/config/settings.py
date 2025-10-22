"""
MLflow Service Settings Configuration

Configuración independiente para el servicio MLflow.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class MLflowServiceSettings(BaseSettings):
    """Configuración específica para el servicio MLflow."""

    def __init__(self, **data):
        super().__init__(**data)
        import logging
        logger = logging.getLogger("mlflow_service")
        logger.info(f"[Settings] PORT (env): {self.PORT}")
        logger.info(f"[Settings] MLFLOW_TRACKING_PORT (default): {self.MLFLOW_TRACKING_PORT}")
        logger.info(f"[Settings] Effective Port: {self.effective_port}")

    # MLflow Server Configuration
    MLFLOW_TRACKING_PORT: int = Field(5001, env="MLFLOW_TRACKING_PORT")
    MLFLOW_HOST: str = Field("0.0.0.0", env="MLFLOW_HOST")
    
    # Cloud Run compatibility - PORT variable override
    PORT: Optional[int] = Field(None, env="PORT")
    
    # PostgreSQL Backend Store (sin fallbacks - debe estar configurado)
    POSTGRES_HOST: str = Field(..., env="POSTGRES_HOST")
    POSTGRES_PORT: int = Field(..., env="POSTGRES_PORT")
    POSTGRES_DB: str = Field(..., env="POSTGRES_DB")
    POSTGRES_USER: str = Field(..., env="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(..., env="POSTGRES_PASSWORD")
    MLFLOW_POSTGRES_CONNECTION_STRING: Optional[str] = Field(None, env="MLFLOW_POSTGRES_CONNECTION_STRING")
  
    # Artifact Storage (Google Cloud Storage) (sin fallbacks - debe estar configurado)
    MLFLOW_BUCKET_LOCATION: str = Field(..., env="MLFLOW_BUCKET_LOCATION")
    MLFLOW_FOLDER_LOCATION: str = Field("mlflow-artifacts-v1", env="MLFLOW_FOLDER_LOCATION")
    
    # GCP Configuration (sin fallbacks - debe estar configurado)
    GCP_PROJECT: str = Field(..., env="GCP_PROJECT")
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(None, env="GOOGLE_APPLICATION_CREDENTIALS")
    USE_GCP_INTERACTIVE_AUTH: bool = Field(False, env="USE_GCP_INTERACTIVE_AUTH")
    
    # Logging Configuration
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    LOG_FORMAT: str = Field("%(asctime)s - %(name)s - %(levelname)s - %(message)s", env="LOG_FORMAT")
    
    # Environment Configuration
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }
    
    # Properties
    @property
    def backend_store_uri(self) -> str:
        """Construye la URI de conexión a PostgreSQL.
        
        Prioridad:
        1. Si MLFLOW_POSTGRES_CONNECTION_STRING existe y no está vacío, usarlo
        2. Si no, construir manualmente con las variables individuales de PostgreSQL
        """
        # Verificar si existe el connection string completo
        if self.MLFLOW_POSTGRES_CONNECTION_STRING and self.MLFLOW_POSTGRES_CONNECTION_STRING.strip():
            # Limpiar comillas si las tiene
            connection_string = self.MLFLOW_POSTGRES_CONNECTION_STRING.strip().strip("'\"")
            return connection_string
        
        # Construir manualmente con variables individuales
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    @property
    def artifact_root(self) -> str:
        """Construye la ubicación completa de artefactos."""
        bucket_location = self.MLFLOW_BUCKET_LOCATION
        folder_location = self.MLFLOW_FOLDER_LOCATION
        
        # Si el bucket_location ya contiene el folder_location, no agregarlo de nuevo
        if folder_location and folder_location in bucket_location.split('/'):
            return bucket_location
        
        # Construir la ruta normal
        if not bucket_location.endswith('/'):
            return f"{bucket_location}/{folder_location}"
        return f"{bucket_location}{folder_location}"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT.lower() == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"
    
    @property
    def gcs_bucket_name(self) -> str:
        """Extract bucket name from MLflow bucket location."""
        if not self.MLFLOW_BUCKET_LOCATION.startswith('gs://'):
            raise ValueError(f"MLFLOW_BUCKET_LOCATION debe comenzar con 'gs://': {self.MLFLOW_BUCKET_LOCATION}")
        
        parts = self.MLFLOW_BUCKET_LOCATION[5:].split('/', 1)
        if not parts[0]:
            raise ValueError(f"No se pudo extraer el nombre del bucket de: {self.MLFLOW_BUCKET_LOCATION}")
        
        return parts[0]
    
    @property
    def effective_port(self) -> int:
        """Retorna el puerto efectivo, priorizando PORT (Cloud Run) sobre MLFLOW_TRACKING_PORT."""
        return self.PORT if self.PORT is not None else self.MLFLOW_TRACKING_PORT


# Crear instancia global
settings = MLflowServiceSettings()