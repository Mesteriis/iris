FROM python:3.14.2

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY ha/addon/iris/run.sh /run.sh

RUN chmod +x /run.sh

WORKDIR /app/backend

EXPOSE 8000

CMD ["/run.sh"]
