FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py finance_mcp.py pdf_mcp.py evidence.py agents.py report_chart.py inputs.py local_rpc.py ./
COPY demo ./demo
ENTRYPOINT ["python", "main.py"]
CMD ["--demo"]
