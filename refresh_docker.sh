#!/bin/bash

# Stop and remove the old container
docker stop finly-app 2>/dev/null
docker rm finly-app 2>/dev/null

# Build a new image
docker build -t finly:latest .

# Run the new container (update volumes/ports as needed)
docker run -d --name finly-app -p 5000:5000 \
  -v "$PWD/portfolio.db:/app/portfolio.db" \
  finly:latest

echo "Finly container refreshed and running!"