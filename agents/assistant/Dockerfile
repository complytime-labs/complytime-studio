# SPDX-License-Identifier: Apache-2.0
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY callbacks.py .
COPY event_converter.py .
COPY prompt.md .
COPY prompts/ /app/prompts/

COPY skills/ /app/skills/

EXPOSE 8080

CMD ["python", "main.py"]
