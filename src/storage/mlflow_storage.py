"""
MLflow Storage Manager

Gestión de almacenamiento para el servicio MLflow independiente.
"""

import logging
import psycopg2
from psycopg2 import sql
from typing import Optional
from src.config.settings import settings

logger = logging.getLogger(__name__)


class MLflowStorageManager:
    """Gestor de almacenamiento para MLflow."""
    
    def __init__(self):
        self.settings = settings
    
    def get_backend_store_uri(self) -> str:
        """
        Obtiene la URI del backend store.
        
        Returns:
            str: URI de conexión a PostgreSQL
        """
        # Verificar conexión antes de devolver la URI
        if self._check_postgresql_connection():
            logger.info("✅ Conexión a PostgreSQL verificada")
            return self.settings.backend_store_uri
        else:
            logger.error("❌ No se pudo conectar a PostgreSQL")
            raise ConnectionError("No se puede conectar a la base de datos PostgreSQL")
    
    def _check_postgresql_connection(self) -> bool:
        """
        Verifica la conexión a PostgreSQL.
        
        Returns:
            bool: True si la conexión es exitosa
        """
        try:
            string_connection = self.settings.MLFLOW_POSTGRES_CONNECTION_STRING

            # Intentar conectar con psycopg2
            conn = psycopg2.connect(string_connection)

            # Probar una consulta simple
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            
            conn.close()
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Error conectando a PostgreSQL: {e}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado verificando PostgreSQL: {e}")
            return False
    
    def initialize_database(self) -> bool:
        """
        Verifica que la conexión a la base de datos es posible.
        
        Returns:
            bool: True si la inicialización fue exitosa
        """
        try:
            # En un entorno de desarrollo o producción con bases de datos gestionadas,
            # asumimos que la base de datos ya existe. Solo verificamos la conexión.
            logger.info(f"Verificando conexión a la base de datos en {self.settings.POSTGRES_HOST}...")
            return self._check_postgresql_connection()
            
        except Exception as e:
            logger.error(f"Error inicializando la base de datos: {e}")
            return False
    
    def _create_database_if_not_exists(self) -> None:
        """Crea la base de datos MLflow si no existe."""
        try:
            # Conectar a la base de datos por defecto para crear la base de datos MLflow
            conn = psycopg2.connect(
                host=self.settings.POSTGRES_HOST,
                port=self.settings.POSTGRES_PORT,
                database="postgres",  # Base de datos por defecto
                user=self.settings.POSTGRES_USER,
                password=self.settings.POSTGRES_PASSWORD
            )
            conn.autocommit = True
            
            with conn.cursor() as cursor:
                # Verificar si la base de datos existe
                cursor.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (self.settings.POSTGRES_DB,)
                )
                
                if not cursor.fetchone():
                    # Crear la base de datos
                    cursor.execute(
                        sql.SQL("CREATE DATABASE {}").format(
                            sql.Identifier(self.settings.POSTGRES_DB)
                        )
                    )
                    logger.info(f"✅ Base de datos '{self.settings.POSTGRES_DB}' creada")
                else:
                    logger.info(f"✅ Base de datos '{self.settings.POSTGRES_DB}' ya existe")
            
            conn.close()
            
        except Exception as e:
            logger.warning(f"No se pudo crear la base de datos: {e}")
            # Continuar, puede que ya exista o el usuario no tenga permisos
    
    def get_tracking_uri(self) -> str:
        """
        Obtiene la URI de tracking de MLflow.
        
        Returns:
            str: URI de tracking
        """
        return f"http://{self.settings.MLFLOW_HOST}:{self.settings.MLFLOW_TRACKING_PORT}"
    
    def cleanup(self):
        """Limpieza de recursos (para compatibilidad)."""
        pass


# Crear instancia global
mlflow_storage_manager = MLflowStorageManager() 