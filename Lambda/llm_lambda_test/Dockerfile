# Use AWS Lambda Python base image
FROM amazon/aws-lambda-python:3.11

# Set working dir inside container
WORKDIR /var/task

# Copy requirements first (to leverage Docker cache)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

# Copy the rest of your Lambda code
COPY . .

# Set Lambda handler (file.function_name)
# Example: if you have lambda_handler.py with def lambda_handler(event, context)
CMD ["lambda_handler.lambda_handler"]
