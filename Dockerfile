FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the standard Flask port
EXPOSE 5000

# Add a healthcheck for the Flask endpoint
HEALTHCHECK CMD curl --fail http://localhost:5000/ || exit 1

# Run the app using Gunicorn (Production server)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]