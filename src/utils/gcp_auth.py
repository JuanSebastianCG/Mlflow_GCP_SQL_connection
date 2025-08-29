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
import google.auth
from google.cloud import secretmanager
from src.config.settings import settings

logger = logging.getLogger(__name__)


class GCPAuthManager:
    """Gestor de autenticación GCP para MLflow."""
    
    def __init__(self):
        """
        Inicializa el gestor de autenticación GCP.
        Prioriza GOOGLE_APPLICATION_CREDENTIALS, luego Application Default Credentials.
        """
        self.logger = logging.getLogger(__name__)
        self.credentials = None
        self.project_id = None
        self.settings = settings
        self.temp_credentials_file: Optional[str] = None
        
        self.logger.info("🔄 Configurando acceso a GCP...")
        self._setup_credentials()
    
    def _setup_credentials(self):
        """
        Configura las credenciales de GCP priorizando GOOGLE_APPLICATION_CREDENTIALS.
        """
        try:
            # Prioridad 1: GOOGLE_APPLICATION_CREDENTIALS
            credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if credentials_path and os.path.exists(credentials_path):
                self.logger.info(f"🔑 Usando credenciales desde GOOGLE_APPLICATION_CREDENTIALS: {credentials_path}")
                self.credentials, self.project_id = google.auth.load_credentials_from_file(credentials_path)
                self.logger.info(f"✅ Credenciales cargadas exitosamente para proyecto: {self.project_id}")
                return
            
            # Prioridad 2: Application Default Credentials
            self.logger.info("🔄 Intentando usar Application Default Credentials...")
            self.credentials, self.project_id = google.auth.default()
            self.logger.info(f"✅ ADC configuradas exitosamente para proyecto: {self.project_id}")
            
        except Exception as e:
            self.logger.error(f"❌ Error configurando credenciales GCP: {e}")
            raise
    
    def _ensure_valid_credentials_path(self):
        """
        Verifica si la ruta de GOOGLE_APPLICATION_CREDENTIALS es válida.
        Si no lo es, la elimina del entorno para permitir métodos de autenticación alternativos.
        """
        creds_path_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path_env and not os.path.exists(creds_path_env):
            logger.warning(
                f"⚠️ La ruta de GOOGLE_APPLICATION_CREDENTIALS ('{creds_path_env}') no existe. "
                "Se eliminará para permitir otros métodos de autenticación de GCP (como ADC)."
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
        
        # 3. Intentar autenticación con Application Default Credentials (ADC)
        # Esto es útil para desarrollo local con `gcloud auth login`
        if self.settings.USE_GCP_INTERACTIVE_AUTH:
            logger.info("🔄 Intentando autenticación con Application Default Credentials (ADC)...")
            try:
                credentials, project = google.auth.default()
                logger.info(f"✅ Credenciales ADC encontradas para el proyecto: {project}")
                # No necesitamos un archivo de credenciales aquí, ya que ADC maneja la autenticación directamente.
                return None # Indicar que ADC fue exitoso y las credenciales están configuradas globalmente
            except Exception as e:
                logger.warning(f"⚠️ Fallo al obtener credenciales ADC: {e}")
                logger.warning("Asegúrate de haber ejecutado `gcloud auth application-default login` o `gcloud auth login` y configurado el proyecto.")

        # Si no se encontró ninguna credencial, registrar un error y retornar None
        logger.error("❌ No se encontraron credenciales válidas para GCP")
        return None
        
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
    
    def validate_gcs_access(self, bucket_name: str) -> bool:
        """
        Valida el acceso al bucket de GCS usando las credenciales configuradas.
        
        Args:
            bucket_name: Nombre del bucket a validar
            
        Returns:
            True si el acceso es válido, False en caso contrario
        """
        try:
            client = self.get_gcs_client()
            bucket = client.bucket(bucket_name)
            
            # Intentar crear un objeto de prueba
            test_blob_name = f"mlflow-test-{int(time.time())}.txt"
            blob = bucket.blob(test_blob_name)
            
            # Escribir contenido de prueba
            blob.upload_from_string("test")
            self.logger.info(f"✅ Escritura exitosa en bucket '{bucket_name}'")
            
            # Leer el contenido
            content = blob.download_as_text()
            if content == "test":
                self.logger.info(f"✅ Lectura exitosa desde bucket '{bucket_name}'")
            
            # Limpiar el objeto de prueba
            blob.delete()
            self.logger.info(f"✅ Validación completa del bucket '{bucket_name}'")
            
            return True
                
        except Exception as e:
            self.logger.error(f"❌ Error validando acceso a GCS: {e}")
            return False
    
    def get_gcs_client(self):
        """Obtiene un cliente de Google Cloud Storage con las credenciales configuradas."""
        try:
            from google.cloud import storage
            
            client = storage.Client(
                credentials=self.credentials,
                project=self.project_id
            )
            self.logger.info("✅ Cliente GCS creado exitosamente")
            return client
                
        except Exception as e:
            self.logger.error(f"❌ Error creando cliente GCS: {e}")
            raise
    
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