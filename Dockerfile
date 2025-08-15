# MLflow Service Dockerfile
FROM python:3.11-slim

# Configurar variables de entorno
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/src

# Crear directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Crear directorio para credenciales
RUN mkdir -p /app/credentials

# Copiar código fuente
COPY src/ /app/src/

# Crear usuario no root para seguridad
RUN groupadd -r mlflow && useradd -r -g mlflow mlflow
RUN chown -R mlflow:mlflow /app
USER mlflow

# Exponer puerto MLflow
EXPOSE 5001

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5001/health', timeout=10)" || exit 1

# Comando por defecto
CMD ["python", "-m", "src.main"] 