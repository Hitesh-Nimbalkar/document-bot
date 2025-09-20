# Use Nginx to serve static files
FROM nginx:alpine

# Remove Nginx default static content
RUN rm -rf /usr/share/nginx/html/*

# Copy your frontend files (index.html, CSS, JS, etc.)
COPY . /usr/share/nginx/html/

# Expose Nginx default port
EXPOSE 80

# Nginx starts automatically in this base image
