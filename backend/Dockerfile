# Fallback build path — use only if Render's native Python runtime fails to
# launch chromium because of missing system libraries. To switch:
#   1. Render dashboard -> flux-api -> Settings -> Runtime: change to Docker
#   2. Set Dockerfile path: backend/Dockerfile
#   3. Clear Build Command and Start Command (Dockerfile owns both)
#   4. Save -> redeploys with this image (chromium + all deps pre-installed)

FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

ENV PORT=10000
EXPOSE 10000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
