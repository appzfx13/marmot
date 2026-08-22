FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    netcat-openbsd \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

COPY . /app/

# Convert entrypoint to Unix format, move to a system path to avoid volume overwrite, 
# and ensure it is executable
RUN dos2unix /app/entrypoint.sh \
    && mv /app/entrypoint.sh /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh

# Point ENTRYPOINT to the system path
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]