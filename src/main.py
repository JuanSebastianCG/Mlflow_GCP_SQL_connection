#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MLflow Service - Main Entry Point

Servicio independiente de MLflow para el orquestador de modelos ML.
"""

import os
import sys
import signal
import logging
import subprocess
import socket
import time
import threading
from urllib.parse import urlparse
from typing import Optional

from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Añadir el directorio raíz del proyecto a sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

class MigrationLogFilter(logging.Filter):
    """Filtro para suprimir logs repetitivos de migración de MLflow."""
    def filter(self, record):
        msg = record.getMessage()
        # Filtrar solo los mensajes que vienen del subproceso del servidor MLflow
        if "[MLflow Server]" in msg:
            # Palabras clave para identificar y suprimir logs de migración ruidosos
            filter_out_keywords = [
                "alembic.runtime.migration",
                "mlflow.store.db.utils",
                "Creating initial MLflow database tables",
                "Updating database tables",
                "Task queue depth is"
            ]
            # Si alguna palabra clave está en el mensaje, no lo muestres
            if any(keyword in msg for keyword in filter_out_keywords):
                return False
        return True

logger = logging.getLogger("mlflow_service")
# Añadir el filtro al logger principal
logger.addFilter(MigrationLogFilter())

# Importar configuración y utilidades
from src.config.settings import settings
from src.utils.gcp_auth import gcp_auth_manager

# Variables globales
mlflow_process: Optional[subprocess.Popen] = None


def log_subprocess_output(pipe, log_level):
    """Lee y registra la salida de un subproceso línea por línea."""
    try:
        for line in iter(pipe.readline, ''):
            logger.log(log_level, f"[MLflow Server] {line.strip()}")
    except Exception as e:
        logger.warning(f"Error leyendo la salida del subproceso: {e}")
    finally:
        if pipe:
            pipe.close()

def setup_signal_handlers():
    """Configura los manejadores de señales para terminación limpia."""
    
    def handle_termination(sig, frame):
        """Manejador de señales para terminar limpiamente."""
        global mlflow_process
        
        logger.info("🛑 Recibida señal de terminación. Deteniendo servidor MLflow...")
        
        # Terminar proceso de MLflow
        if mlflow_process:
            try:
                mlflow_process.terminate()
                exit_code = mlflow_process.wait(timeout=10)
                logger.info(f"✅ Servidor MLflow detenido. Código de salida: {exit_code}")
            except subprocess.TimeoutExpired:
                logger.warning("⚠️ Timeout. Forzando terminación...")
                mlflow_process.kill()
                mlflow_process.wait()
                logger.info("✅ Proceso MLflow terminado forzosamente")
            except Exception as e:
                logger.error(f"❌ Error terminando proceso MLflow: {e}")
        
        # Limpiar recursos
        try:
            gcp_auth_manager.cleanup()
            logger.info("✅ Limpieza completada")
        except Exception as e:
            logger.error(f"❌ Error durante limpieza: {e}")
        
        logger.info("✅ Servicio MLflow detenido completamente")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handle_termination)
    signal.signal(signal.SIGTERM, handle_termination)


def verify_mlflow_installation() -> bool:
    """
    Verifica que MLflow esté instalado correctamente.
    
    Returns:
        bool: True si MLflow está instalado
    """
    try:
        import mlflow
        logger.info(f"✅ MLflow versión {mlflow.__version__} detectado")
        return True
    except ImportError:
        logger.error("❌ MLflow no está instalado")
        return False


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """
    Verifica si un puerto está en uso.
    
    Args:
        port: Número de puerto
        host: Host para verificar
        
    Returns:
        bool: True si el puerto está en uso
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) == 0


def wait_for_mlflow_server(host: str, port: int, timeout: int = 30) -> bool:
    """
    Espera a que el servidor MLflow responda.
    
    Args:
        host: Host del servidor
        port: Puerto del servidor
        timeout: Tiempo máximo de espera en segundos
        
    Returns:
        bool: True si el servidor responde
    """
    logger.info(f"🔄 Esperando servidor MLflow en {host}:{port}")
    
    check_host = "127.0.0.1" if host == "0.0.0.0" else host
    
    for _ in range(timeout):
        if mlflow_process and mlflow_process.poll() is not None:
            logger.error(f"❌ El proceso de MLflow terminó inesperadamente. Revisa los logs de '[MLflow Server]'.")
            return False

        if is_port_in_use(port, check_host):
            logger.info(f"✅ Servidor MLflow disponible en {host}:{port}")
            return True
        time.sleep(1)
    
    logger.error(f"❌ Servidor MLflow no respondió en {timeout} segundos")
    return False

def upgrade_database_schema() -> bool:
    """
    Actualiza el esquema de la base de datos MLflow a la última versión.
    Es un paso crucial para evitar errores de migración concurrentes dentro
    del servidor MLflow, especialmente en Windows.
    
    Returns:
        bool: True si la actualización fue exitosa o no fue necesaria.
    """
    logger.info("🔄 Verificando y actualizando el esquema de la base de datos MLflow...")
    
    try:
        backend_store_uri = settings.backend_store_uri
        cmd = ['mlflow', 'db', 'upgrade', backend_store_uri]
        
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8',
            errors='replace'
        )
        
        stdout = process.stdout.lower()
        if "upgraded successfully" in stdout:
            logger.info("✅ Esquema de la base de datos actualizado exitosamente.")
        elif "is up to date" in stdout or "alembic_version" in stdout:
            logger.info("✅ El esquema de la base de datos ya está actualizado.")
        else:
            logger.info(f"Resultado de la actualización de la BD: {process.stdout.strip()}")
        return True

    except subprocess.CalledProcessError as e:
        stderr_lower = e.stderr.lower()
        if "does not exist" in stderr_lower or "OperationalError" in e.stderr:
            logger.warning("⚠️ La base de datos parece no existir aún. Se creará al iniciar el servidor.")
            return True
        
        logger.error("❌ Error actualizando el esquema de la base de datos.")
        logger.error(f"   Comando: {' '.join(e.cmd)}")
        logger.error(f"   Salida de error:\n{e.stderr}")
        return False
    except Exception as e:
        logger.error(f"❌ Error inesperado durante la actualización del esquema: {e}")
        return False

def start_mlflow_server() -> bool:
    """
    Inicia el servidor MLflow.
    
    Returns:
        bool: True si el servidor se inició correctamente
    """
    global mlflow_process
    
    # Configurar host y puerto
    host = settings.MLFLOW_HOST
    port = settings.MLFLOW_TRACKING_PORT
    
    logger.info(f"🚀 Iniciando servidor MLflow")
    logger.info(f"   Host: {host}")
    logger.info(f"   Puerto: {port}")
    logger.info(f"   Artifact root: {settings.artifact_root}")
    logger.info(f"   Backend store: PostgreSQL")
    
    # Verificar que el puerto esté libre
    if is_port_in_use(port, host):
        logger.error(f"❌ Puerto {port} ya está en uso")
        return False
    
    # Obtener backend store URI directamente de la configuración
    backend_store_uri = settings.backend_store_uri
    if not backend_store_uri:
        logger.error("❌ La URI del backend store no está configurada (MLFLOW_POSTGRES_CONNECTION_STRING).")
        return False
    logger.info(f"✅ Backend store URI configurada.")
    
    # Configurar credenciales GCP si es necesario
    if settings.artifact_root.startswith("gs://"):
        logger.info("🔑 Configurando credenciales GCP...")
        gcp_auth_manager.setup_gcp_credentials()
        
        # Validar credenciales
        if gcp_auth_manager.validate_gcs_credentials():
            logger.info("✅ Credenciales GCP validadas")
        else:
            logger.warning("⚠️ No se pudieron validar las credenciales GCP")
    
    # Construir comando MLflow
    cmd = [
        'mlflow', 'server',
        '--backend-store-uri', backend_store_uri,
        '--default-artifact-root', settings.artifact_root,
        '--host', host,
        '--port', str(port),
        '--serve-artifacts'
    ]
    
    logger.info(f"🔧 Comando: {' '.join(cmd)}")
    
    # En Windows, waitress no soporta 'workers'. Para evitar que MLflow falle,
    # creamos un entorno para el subproceso que no incluya la variable de
    # entorno en conflicto (`MLFLOW_WORKERS`), que MLflow lee internamente.
    env = os.environ.copy()
    if sys.platform == "win32":
        env.pop('MLFLOW_WORKERS', None)

    # Iniciar proceso MLflow
    try:
        mlflow_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )

        # Iniciar hilos para leer stdout y stderr sin bloquear
        stdout_thread = threading.Thread(target=log_subprocess_output, args=(mlflow_process.stdout, logging.INFO))
        stderr_thread = threading.Thread(target=log_subprocess_output, args=(mlflow_process.stderr, logging.ERROR))
        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()
        
        logger.info(f"✅ Proceso MLflow iniciado (PID: {mlflow_process.pid})")
        
        # Esperar a que el servidor esté disponible
        if wait_for_mlflow_server(host, port, timeout=30):
            logger.info(f"🎉 MLflow UI disponible en: http://{host}:{port}")
            return True
        else:
            logger.error("❌ Timeout esperando que MLflow se inicie")
            if mlflow_process and mlflow_process.poll() is None:
                mlflow_process.terminate()
            return False
            
    except Exception as e:
        logger.error(f"❌ Error iniciando MLflow: {e}")
        return False


def main():
    """Función principal del servicio MLflow."""
    logger.info("🔄 Iniciando MLflow Service")
    
    # Configurar manejadores de señales
    setup_signal_handlers()
    
    # Verificar instalación de MLflow
    if not verify_mlflow_installation():
        sys.exit(1)

    # Iniciar servidor MLflow.
    # El propio comando `mlflow server` gestionará la conexión a la base de datos
    # y las migraciones. El filtro de logs se encargará de la verbosidad.
    if start_mlflow_server():
        logger.info("✅ Servicio MLflow iniciado correctamente")
        
        try:
            # Mantener el proceso en ejecución
            mlflow_process.wait()
        except KeyboardInterrupt:
            logger.info("🛑 Interrupción de teclado recibida")
        except Exception as e:
            logger.error(f"❌ Error durante ejecución: {e}")
    else:
        logger.error("❌ Error iniciando servicio MLflow")
        sys.exit(1)


if __name__ == '__main__':

    main() 