FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy requirements and install (as root, before dropping privileges)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Run as a non-root user (defense in depth — nothing here needs root;
# outputs/ is created at runtime by the app itself under /app).
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose the standard Flask port
EXPOSE 5000

# Stdlib-only healthcheck: python:3.10-slim has no curl installed (the
# previous `curl --fail ...` healthcheck always failed with "curl: not
# found"). This is mainly useful for local `docker run`/compose — Cloud
# Run ignores Dockerfile HEALTHCHECK entirely.
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/', timeout=3)" || exit 1

# Run the app using Gunicorn (Production server). Timeout raised well
# above observed worst-case book-generation time (~2-3 min) so a slow
# request isn't killed mid-generation after most images are already paid
# for, forcing a full-cost retry (PERF/OPS-3 interim). The durable fix is
# the async job model in the Next.js migration — see NextJSWebDesign.md.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "300", "app:app"]