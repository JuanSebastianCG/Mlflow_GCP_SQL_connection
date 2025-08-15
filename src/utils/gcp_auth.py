"""
GCP Authentication Utilities for MLflow Service

Utilidades de autenticación para Google Cloud Platform.
"""

import os
import json
import logging
import tempfile
import time
from typing import Optional, Dict, Any
from google.cloud import secretmanager
from src.config.settings import settings

logger = logging.getLogger(__name__)


class GCPAuthManager:
    """Gestor de autenticación GCP para MLflow."""
    
    def __init__(self):
        self.settings = settings
        self.temp_credentials_file: Optional[str] = None
    
    def _ensure_valid_credentials_path(self):
        """
        Verifica si la ruta de GOOGLE_APPLICATION_CREDENTIALS es válida.
        Si no lo es, la elimina del entorno para permitir métodos de autenticación alternativos.
        """
        creds_path_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path_env and not os.path.exists(creds_path_env):
            logger.warning(
                f"⚠️ La ruta de GOOGLE_APPLICATION_CREDENTIALS ('{creds_path_env}') no existe. "
                "Se intentarán otros métodos de autenticación de GCP."
            )
            del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
            # También actualizar el valor en la configuración para consistencia
            if self.settings.GOOGLE_APPLICATION_CREDENTIALS == creds_path_env:
                self.settings.GOOGLE_APPLICATION_CREDENTIALS = None

    def setup_gcp_credentials(self) -> Optional[str]:
        """
        Configura las credenciales de GCP para acceso al bucket.
        
        Returns:
            Optional[str]: Ruta al archivo de credenciales o None si no se pudo configurar
        """
        self._ensure_valid_credentials_path()

        # 1. Verificar si ya hay credenciales configuradas
        creds_path = self.settings.GOOGLE_APPLICATION_CREDENTIALS
        if creds_path and os.path.exists(creds_path):
            logger.info(f"✅ Usando credenciales GCP existentes: {creds_path}")
            return creds_path
        
        # 2. Intentar obtener credenciales de Secret Manager
        if self.settings.GCP_PROJECT:
            secret_creds = self._get_credentials_from_secret_manager()
            if secret_creds:
                return secret_creds
        
        # 3. Verificar autenticación interactiva (para desarrollo)
        if self.settings.USE_GCP_INTERACTIVE_AUTH:
            logger.info("🔄 Usando autenticación interactiva de GCP")
            return None  # MLflow usará las credenciales por defecto
        
        logger.error("❌ No se encontraron credenciales válidas para GCP")
        return None
    
    def _get_credentials_from_secret_manager(self) -> Optional[str]:
        """
        Obtiene credenciales desde Secret Manager.
        
        Returns:
            Optional[str]: Ruta al archivo temporal de credenciales
        """
        try:
            logger.info("🔍 Intentando obtener credenciales desde Secret Manager...")
            
            # Crear cliente de Secret Manager
            client = secretmanager.SecretManagerServiceClient()
            
            # Nombre del secreto
            secret_id = "GOOGLE_APPLICATION_CREDENTIALS_MLFLOWSA"
            project_id = self.settings.GCP_PROJECT
            secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            
            logger.info(f"🔍 Buscando secreto: {secret_name}")
            
            # Obtener el secreto
            response = client.access_secret_version(request={"name": secret_name})
            service_account_json = response.payload.data.decode("UTF-8")
            
            # Verificar que es JSON válido
            try:
                json.loads(service_account_json)
            except json.JSONDecodeError:
                logger.error("❌ El contenido del secreto no es un JSON válido")
                return None
            
            # Crear archivo temporal
            fd, temp_file = tempfile.mkstemp(suffix='.json', prefix='mlflow_gcp_creds_')
            with os.fdopen(fd, 'w') as f:
                f.write(service_account_json)
            
            # Guardar referencia para limpieza posterior
            self.temp_credentials_file = temp_file
            
            # Configurar variable de entorno
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_file
            logger.info(f"✅ Credenciales GCP configuradas desde Secret Manager")
            
            return temp_file
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo credenciales de Secret Manager: {e}")
            return None
    
    def validate_gcs_credentials(self, bucket_name: Optional[str] = None) -> bool:
        """
        Valida las credenciales de GCS.
        
        Args:
            bucket_name: Nombre del bucket a validar
            
        Returns:
            bool: True si las credenciales son válidas
        """
        self._ensure_valid_credentials_path()
        
        if not bucket_name:
            # Extraer nombre del bucket desde configuración
            if self.settings.MLFLOW_BUCKET_LOCATION.startswith("gs://"):
                bucket_name = self.settings.gcs_bucket_name
            else:
                logger.warning("⚠️ No se proporcionó nombre de bucket para validación")
                return False
        
        try:
            from google.cloud import storage
            
            # Crear cliente de storage
            client = storage.Client()
            logger.info(f"✅ Cliente GCS creado exitosamente")
            
            # Verificar acceso al bucket
            bucket = client.get_bucket(bucket_name)
            logger.info(f"✅ Acceso al bucket '{bucket_name}' verificado")
            
            # Probar listado de objetos
            blobs = list(bucket.list_blobs(max_results=1))
            logger.info(f"✅ Permisos de lectura verificados")
            
            # Probar escritura con un archivo de prueba
            test_blob_name = f"test_mlflow_auth_{int(time.time())}.txt"
            test_blob = bucket.blob(test_blob_name)
            test_blob.upload_from_string("Test file for MLflow authentication")
            
            # Eliminar archivo de prueba
            test_blob.delete()
            logger.info(f"✅ Permisos de escritura verificados")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error validando credenciales GCS: {e}")
            return False
    
    def cleanup(self) -> None:
        """Limpia archivos temporales de credenciales."""
        if self.temp_credentials_file and os.path.exists(self.temp_credentials_file):
            try:
                os.unlink(self.temp_credentials_file)
                logger.info(f"✅ Archivo temporal de credenciales eliminado")
                self.temp_credentials_file = None
            except Exception as e:
                logger.error(f"❌ Error eliminando archivo temporal: {e}")


# Crear instancia global
gcp_auth_manager = GCPAuthManager() 