# Not wired to a deploy target yet — included for later. SQLite needs a
# mounted volume for persistence in any real containerized deployment.

FROM node:20-alpine AS client-build
WORKDIR /app/client
COPY client/package.json client/package-lock.json* ./
RUN npm install
COPY client/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server/ server/
COPY --from=client-build /app/client/dist client/dist

ENV FLASK_ENV=production
EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "server.wsgi:app"]
