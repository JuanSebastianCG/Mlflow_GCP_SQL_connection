#!/usr/bin/env python3
# -*- coding: utf-8 -*
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

logger = logging.getLogger("mlflow_service")

# Importar configuración y utilidades
from src.config.settings import settings

# Ajustar nivel de logging según configuración (p. ej., LOG_LEVEL=WARNING en producción)

def _to_log_level(name: str) -> int:
    try:
        return getattr(logging, str(name).upper())
    except Exception:
        return logging.INFO

_root_logger = logging.getLogger()
_desired_level = _to_log_level(getattr(settings, "LOG_LEVEL", "INFO"))
_root_logger.setLevel(_desired_level)
logger.setLevel(_desired_level)

# Variables globales
mlflow_process: Optional[subprocess.Popen] = None
# Evento global para detener el GC en segundo plano con gracia
_gc_stop_event = threading.Event()


def log_subprocess_output(pipe):
    """Lee y registra la salida de un subproceso línea por línea, clasificando el nivel por contenido."""
    try:
        for line in iter(pipe.readline, ''):
            text = line.strip()
            lower = text.lower()
            level = logging.INFO
            # Clasificar el nivel en función del contenido de la línea
            if (
                "traceback (most recent call last):" in lower
                or lower.startswith("error")
                or " error " in lower
                or "[error" in lower
                or " critical " in lower
                or "fatal" in lower
            ):
                level = logging.ERROR
            elif lower.startswith("warning") or " warn " in lower or "[warning" in lower:
                level = logging.WARNING
            # Registrar con el nivel determinado
            logger.log(level, f"[MLflow Server] {text}")
    except Exception as e:
        logger.warning(f"Error leyendo la salida del subproceso: {e}")
    finally:
        if pipe:
            pipe.close()


def _run_mlflow_gc_loop(interval_seconds: int, older_than: str):
    """Bucle en segundo plano que ejecuta `mlflow gc` periódicamente.

    Lee la URI del backend desde settings.backend_store_uri. Si no está
    configurada, registra advertencia y termina el bucle.
    """
    backend_store_uri = settings.backend_store_uri
    if not backend_store_uri:
        logger.warning("♻️ GC deshabilitado: backend_store_uri no configurado.")
        return

    # Construir tracking URI local para el CLI de mlflow gc
    tracking_host = "127.0.0.1" if settings.MLFLOW_HOST in ("0.0.0.0", "::") else settings.MLFLOW_HOST
    tracking_uri = f"http://{tracking_host}:{settings.effective_port}"

    logger.info(
        f"♻️ MLflow GC habilitado: cada {interval_seconds}s, older-than={older_than}, backend={backend_store_uri}, tracking-uri={tracking_uri}"
    )

    # Preparar entorno del subproceso (quitar MLFLOW_WORKERS en Windows por seguridad)
    base_env = os.environ.copy()
    if sys.platform == "win32":
        base_env.pop('MLFLOW_WORKERS', None)
    # Asegurar que el CLI de mlflow vea el tracking URI
    base_env['MLFLOW_TRACKING_URI'] = tracking_uri

    while not _gc_stop_event.is_set():
        try:
            cmd = [
                sys.executable, '-m', 'mlflow', 'gc',
                '--backend-store-uri', backend_store_uri,
                '--older-than', str(older_than),
                '--tracking-uri', tracking_uri
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=base_env,
                check=False
            )
            out = (proc.stdout or '').strip()
            err = (proc.stderr or '').strip()
            if out:
                logger.info(f"[GC] {out}")
            if err:
                # Usa WARNING para no ensuciar con ERROR si no es crítico
                logger.warning(f"[GC] {err}")
        except Exception as e:
            logger.error(f"❌ Error ejecutando GC: {e}")
        # Esperar el siguiente ciclo con posibilidad de salida inmediata
        _gc_stop_event.wait(interval_seconds)


def setup_signal_handlers():
    """Configura los manejadores de señales para terminación limpia."""
    def handle_termination(sig, frame):
        """Manejador de señales para terminar limpiamente."""
        global mlflow_process
        
        logger.info("🛑 Recibida señal de terminación. Deteniendo servidor MLflow y GC...")

        # Detener GC
        try:
            _gc_stop_event.set()
        except Exception:
            pass
        
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
        logger.info("✅ Limpieza completada")
        
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
        import sys as _sys
        logger.info(f"✅ MLflow versión {mlflow.__version__} detectado (módulo: {mlflow.__file__})")
        logger.info(f"   Python ejecutable: {_sys.executable}")
        # Para depuración avanzada, habilitar DEBUG para ver sys.path
        logger.debug(f"   sys.path[0:3]: {_sys.path[:3]} ... (total rutas: {len(_sys.path)})")
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
    Retorna True si la actualización fue exitosa o si no es necesaria aún.
    """
    logger.info("🔄 Verificando y actualizando el esquema de la base de datos MLflow...")

    backend_store_uri = settings.backend_store_uri
    if not backend_store_uri:
        logger.error("❌ La URI del backend store no está configurada (MLFLOW_POSTGRES_CONNECTION_STRING).")
        return False

    try:
        cmd = [sys.executable, '-m', 'mlflow', 'db', 'upgrade', backend_store_uri]
        logger.info(f"Ejecutando comando: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False,
            timeout=60,  # Timeout de 60 segundos
            env=os.environ.copy()
        )

        stdout = (result.stdout or '').strip()
        stderr = (result.stderr or '').strip()

        if result.returncode == 0:
            # Consideramos éxito si el comando terminó correctamente
            if stdout:
                lower = stdout.lower()
                if "upgraded" in lower or "is up to date" in lower or "alembic_version" in lower:
                    logger.info("✅ Esquema de la base de datos actualizado o ya al día.")
                else:
                    logger.info(f"Resultado de la actualización de la BD: {stdout}")
            else:
                logger.info("✅ Esquema de la base de datos actualizado correctamente.")
            return True

        # Si no fue 0, revisar mensajes comunes y decidir si continuar
        lower_err = stderr.lower()
        if "does not exist" in lower_err or "operationalerror" in lower_err:
            logger.warning("⚠️ La base de datos aún no existe o no es accesible; se intentará crear/ajustar al iniciar el servidor.")
            return True

        logger.error("❌ Error actualizando el esquema de la base de datos.")
        if stdout:
            logger.error(f"STDOUT:\n{stdout}")
        if stderr:
            logger.error(f"STDERR:\n{stderr}")
        return False

    except subprocess.TimeoutExpired:
        logger.warning("⚠️ Timeout en la actualización del esquema de la base de datos (60s). Continuando con el inicio del servidor...")
        return True  # Continuamos, el servidor puede crear las tablas si es necesario
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
    port = settings.effective_port
    
    logger.info(f"🚀 Iniciando servidor MLflow")
    logger.info(f"   Host: {host}")
    logger.info(f"   Puerto: {port}")
    logger.info(f"   Artifact root URI: {settings.artifact_root}")
    logger.info(f"   GOOGLE_APPLICATION_CREDENTIALS (env): {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")
    logger.info(f"   MLFLOW_TRACKING_URI (env): {os.getenv('MLFLOW_TRACKING_URI')}")
    logger.info(f"   MLFLOW_ARTIFACT_URI (env): {os.getenv('MLFLOW_ARTIFACT_URI')}")
    
    # Debug: Variables de entorno de PostgreSQL
    logger.info(f"🔍 DEBUG - Variables de entorno PostgreSQL:")
    logger.info(f"   POSTGRES_HOST (env): {os.getenv('POSTGRES_HOST')}")
    logger.info(f"   POSTGRES_PORT (env): {os.getenv('POSTGRES_PORT')}")
    logger.info(f"   POSTGRES_USER (env): {os.getenv('POSTGRES_USER')}")
    logger.info(f"   POSTGRES_DB (env): {os.getenv('POSTGRES_DB')}")
    logger.info(f"   MLFLOW_POSTGRES_CONNECTION_STRING (env): {os.getenv('MLFLOW_POSTGRES_CONNECTION_STRING')}")
    logger.info(f"   settings.POSTGRES_HOST: {settings.POSTGRES_HOST}")
    logger.info(f"   settings.backend_store_uri: {settings.backend_store_uri}")
    
    logger.info(f"   Comprobando si el puerto {port} está en uso en {host}...") # Nuevo log
    
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
    
    # Nota: dejamos que el propio servidor MLflow maneje las credenciales de artefactos
    # mediante --serve-artifacts y --artifacts-destination. No hacemos validación previa
    # ni pruebas de escritura en GCS aquí para evitar efectos secundarios en producción.
    
    # Construir comando MLflow (artifacts server gestionado por el servidor)
    cmd = [
        sys.executable, '-m', 'mlflow', 'server',
        '--backend-store-uri', backend_store_uri,
        '--artifacts-destination', settings.artifact_root,
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
        stdout_thread = threading.Thread(target=log_subprocess_output, args=(mlflow_process.stdout,))
        stderr_thread = threading.Thread(target=log_subprocess_output, args=(mlflow_process.stderr,))
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

    # Pre-actualizar el esquema de la base de datos antes de arrancar el servidor
    # Esto evita errores de Alembic durante el start del server
    if not upgrade_database_schema():
        logger.error("❌ No fue posible actualizar el esquema de la base de datos. Abortando inicio.")
        sys.exit(1)

    # Leer configuración de GC desde variables de entorno (.env)
    gc_enabled = os.getenv("MLFLOW_GC_ENABLED", "true").strip().lower() not in ("0", "false", "no")
    try:
        gc_interval = int(os.getenv("MLFLOW_GC_INTERVAL_SECONDS", "20"))
        if gc_interval <= 0:
            raise ValueError
    except Exception:
        gc_interval = 20
    gc_older_than = os.getenv("MLFLOW_GC_OLDER_THAN", "5m").strip()

    # Iniciar servidor MLflow.
    # El propio comando `mlflow server` gestionará la conexión a la base de datos
    # y las migraciones. El filtro de logs se encargará de la verbosidad.
    if start_mlflow_server():
        logger.info("✅ Servicio MLflow iniciado correctamente")

        # Lanzar GC en segundo plano si está habilitado
        gc_thread = None
        if gc_enabled:
            gc_thread = threading.Thread(
                target=_run_mlflow_gc_loop,
                args=(gc_interval, gc_older_than),
                daemon=True,
                name="mlflow-gc-thread"
            )
            gc_thread.start()
        else:
            logger.info("♻️ MLflow GC deshabilitado por configuración (MLFLOW_GC_ENABLED=false)")
        
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