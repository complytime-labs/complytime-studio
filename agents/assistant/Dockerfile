# SPDX-License-Identifier: Apache-2.0
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY graph.py .
COPY state.py .
COPY router.py .
COPY nodes.py .
COPY tools.py .
COPY validation.py .
COPY delegate.py .
COPY prompt.py .
COPY langgraph.json .
COPY prompt.md .
COPY prompts/ /app/prompts/
COPY skills/ /app/skills/

EXPOSE 8080

CMD ["uvicorn", "graph:graph", "--host", "0.0.0.0", "--port", "8080"]
