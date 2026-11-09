FROM python:3.12-slim

# Evita criação de arquivos .pyc e força flush imediato dos logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instala certificados SSL e ferramentas básicas se necessário
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Cria diretório para persistência do banco SQLite
RUN mkdir -p data

# Por padrão, roda em modo loop a cada 60 minutos
CMD ["python", "main.py", "--loop", "--interval", "60"]

