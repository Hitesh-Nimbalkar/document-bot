# Use Nginx to serve static files
FROM nginx:alpine

# Copy everything from your UI folder (HTML, JS, CSS, images, etc.)
COPY . /usr/share/nginx/html

# Expose nginx default port
EXPOSE 80

# Nginx already starts by default in this base image
