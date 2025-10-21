# MLflow Service

Servicio independiente de MLflow para el orquestador de modelos ML.

## 🚀 Características

- **MLflow Tracking Server**: Servidor de seguimiento de experimentos
- **PostgreSQL Backend**: Base de datos PostgreSQL para metadata
- **Google Cloud Storage**: Almacenamiento de artefactos en GCS
- **Docker**: Contenedor completamente aislado
- **Configuración flexible**: Variables de entorno separadas

## 🏗️ Arquitectura

```
mlflow-service/
├── src/
│   ├── main.py                 # Punto de entrada principal
│   ├── config/
│   │   └── settings.py         # Configuración del servicio
│   ├── storage/
│   │   └── mlflow_storage.py   # Gestión de almacenamiento
│   └── utils/
│       └── gcp_auth.py         # Autenticación GCP
├── docker/
│   └── Dockerfile              # Imagen Docker
├── docker-compose.yml          # Orquestación de servicios
├── requirements.txt            # Dependencias Python
├── .env.example               # Variables de entorno ejemplo
└── README.md                  # Este archivo
```

## 🛠️ Instalación

### Prerrequisitos

- Docker y Docker Compose
- PostgreSQL (puede ejecutarse en Docker)
- Credenciales de Google Cloud para GCS

### Configuración

1. Copiar variables de entorno:
   ```bash
   cp .env.example .env
   ```

2. Editar `.env` con tu configuración:
   ```env
   # MLflow Configuration
   MLFLOW_TRACKING_PORT=5001
   MLFLOW_BUCKET_LOCATION=gs://tu-bucket-mlflow
   MLFLOW_FOLDER_LOCATION=mlflow-artifacts-v1
   
   # PostgreSQL Configuration
   POSTGRES_HOST=postgres
   POSTGRES_PORT=5432
   POSTGRES_DB=mlflow
   POSTGRES_USER=mlflow
   POSTGRES_PASSWORD=mlflow_password
   
   # GCP Configuration
   GCP_PROJECT=tu-proyecto-gcp
   GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gcp-credentials.json
   ```

### Autenticación sin archivo de credenciales (Usuario/Contraseña)

Si no deseas usar un archivo de credenciales para la autenticación de GCP, puedes configurar las variables de entorno directamente con tu usuario y contraseña de la siguiente manera:

```env
# GCP Configuration (Autenticación con usuario/contraseña)
# Asegúrate de que tu cuenta de servicio tenga los roles necesarios (e.g., Storage Admin, BigQuery Data Editor)
# para acceder a los recursos de GCP.
# NOTA: Esta forma de autenticación es menos segura que el uso de un archivo de credenciales
# y solo debe usarse en entornos de desarrollo o pruebas.

GCP_PROJECT=tu-proyecto-gcp
GOOGLE_APPLICATION_CREDENTIALS_TYPE=service_account
GOOGLE_APPLICATION_CREDENTIALS_PROJECT_ID=tu-proyecto-gcp
GOOGLE_APPLICATION_CREDENTIALS_PRIVATE_KEY_ID=tu-private-key-id
GOOGLE_APPLICATION_CREDENTIALS_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nTU_PRIVATE_KEY_AQUI\n-----END PRIVATE KEY-----"
GOOGLE_APPLICATION_CREDENTIALS_CLIENT_EMAIL=tu-cuenta-servicio@tu-proyecto-gcp.iam.gserviceaccount.com
GOOGLE_APPLICATION_CREDENTIALS_CLIENT_ID=tu-client-id
GOOGLE_APPLICATION_CREDENTIALS_AUTH_URI=https://accounts.google.com/o/oauth2/auth
GOOGLE_APPLICATION_CREDENTIALS_TOKEN_URI=https://oauth2.googleapis.com/token
GOOGLE_APPLICATION_CREDENTIALS_AUTH_PROVIDER_X509_CERT_URL=https://www.googleapis.com/oauth2/v1/certs
GOOGLE_APPLICATION_CREDENTIALS_CLIENT_X509_CERT_URL=https://www.googleapis.com/robot/v1/metadata/x509/tu-cuenta-servicio%40tu-proyecto-gcp.iam.gserviceaccount.com
```

**Importante**: Para la conexión a la base de datos PostgreSQL, las credenciales ya se manejan a través de las variables `POSTGRES_USER` y `POSTGRES_PASSWORD` en el archivo `.env`.

### Autenticación con `gcloud auth login`

Si estás ejecutando la aplicación localmente y tienes los permisos adecuados en tu cuenta de Google Cloud, puedes autenticarte utilizando el comando `gcloud auth login` y configurando el proyecto por defecto. Esto permite que la aplicación utilice tus credenciales de usuario para acceder a los servicios de GCP (como Google Cloud Storage).

1.  **Inicia sesión en gcloud:**
    ```bash
    gcloud auth login
    ```

2.  **Configura tu proyecto de GCP (si no lo has hecho ya):**
    ```bash
    gcloud config set project tu-proyecto-gcp
    ```

    Asegúrate de que `tu-proyecto-gcp` coincida con el `GCP_PROJECT` configurado en tu archivo `.env`.

Con estos pasos, la aplicación debería poder autenticarse automáticamente con tus credenciales de usuario de GCP.

## 🚀 Ejecución

### Con Docker Compose (Recomendado)

```bash
# Ejecutar todos los servicios
docker-compose up -d

# Ver logs
docker-compose logs -f mlflow

# Detener servicios
docker-compose down
```

### Manualmente

```bash
# 1. Crear un entorno virtual
python -m venv .venv

# 2. Activar el entorno virtual
# En Windows:
.venv\Scripts\activate
# En macOS/Linux:
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar las variables de entorno
# Asegúrate de tener un archivo .env en la raíz del proyecto con las variables necesarias.
# Puedes usar el .env.example como base y adaptarlo a tu configuración de PostgreSQL y GCS.
# Por ejemplo:
# MLFLOW_TRACKING_PORT=5001
# MLFLOW_HOST=0.0.0.0
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
# POSTGRES_DB=mlflow
# POSTGRES_USER=mlflow
# POSTGRES_PASSWORD=mlflow_password
# MLFLOW_POSTGRES_CONNECTION_STRING="postgresql://mlflow:mlflow_password@localhost:5432/mlflow"
# MLFLOW_BUCKET_LOCATION=gs://tu-bucket-mlflow
# MLFLOW_FOLDER_LOCATION=mlflow-artifacts-v1
# GCP_PROJECT=tu-proyecto-gcp
# GOOGLE_APPLICATION_CREDENTIALS=/ruta/a/tus/credenciales.json

# 5. Ejecutar el servidor MLflow
python src/main.py
```

## 📡 API Endpoints

- **MLflow UI**: `http://localhost:5001`
- **MLflow API**: `http://localhost:5001/api/2.0/mlflow/`

## 🔗 Integración

Este servicio está diseñado para ser usado por el orquestador FastAPI:

```python
# En el proyecto FastAPI
MLFLOW_TRACKING_URI = "http://mlflow-service:5001"
```

## 🛡️ Seguridad

- Red interna Docker para comunicación entre servicios
- Credenciales GCP montadas como volumen
- Variables de entorno para configuración sensible

## 📊 Monitoreo

- Health check endpoint: `http://localhost:5001/health`
- Logs estructurados
- Métricas de contenedor Docker "# Mlflow_GCP_SQL_connection"


C:\Users\jscardenasg.COLOMBIA\Documents\Work\code\Apps\Mlops\Mlflow-Service\.venv\Scripts\activate
python C:\Users\jscardenasg.COLOMBIA\Documents\Work\code\Apps\Mlops\Mlflow-Service\src\main.py
