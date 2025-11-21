FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 mcpuser
USER mcpuser
WORKDIR /home/mcpuser

# Ensure local bin is in PATH
ENV PATH="/home/mcpuser/.local/bin:${PATH}"

# Install Python dependencies
COPY --chown=mcpuser:mcpuser requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy server code
COPY --chown=mcpuser:mcpuser main.py .

# Set the entrypoint to run the MCP server
ENTRYPOINT ["python", "main.py"]