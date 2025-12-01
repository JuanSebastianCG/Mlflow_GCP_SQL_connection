# MLflow Service Dockerfile
FROM python:3.11-slim

# Configurar variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

# Crear directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# (Opcional) EntryPoint eliminado: GC corre desde src.main
# COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Crear directorio para credenciales
RUN mkdir -p /app/credentials

# Copiar código fuente
COPY src/ /app/src/

# Crear usuario no root para seguridad
RUN groupadd -r mlflow && useradd -r -g mlflow mlflow
RUN chown -R mlflow:mlflow /app
USER mlflow

# Exponer puerto para Cloud Run (SIEMPRE usa puerto 8080)
EXPOSE 8080

# Health check para Cloud Run (verifica que la app esté respondiendo)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import os, requests; requests.get(f'http://localhost:8080/health', timeout=10)" || exit 1

# Variables de entorno por defecto para GC (pueden sobrescribirse en runtime)
ENV MLFLOW_GC_ENABLED=true \
    MLFLOW_GC_INTERVAL_SECONDS=20 \
    MLFLOW_GC_OLDER_THAN=5m

# ENTRYPOINT no es necesario; src.main inicia MLflow y el GC en background
# ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Comando por defecto (arranca el servidor en puerto 8080 para Cloud Run)
CMD ["python", "-m", "src.main", "--port", "8080"]