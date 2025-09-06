# Use the official AWS Lambda Python 3.11 base image
FROM public.ecr.aws/lambda/python:3.12

# Set working directory inside the container
WORKDIR /var/task

# Copy requirements.txt if you have dependencies
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Lambda function code
COPY . .
# Set the CMD to your handler (file.function)
# For example, if handler is in app.py and function is lambda_handler:
CMD ["lambda_handler.lambda_handler"]
