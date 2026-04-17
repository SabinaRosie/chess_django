---
title: Sabina Chess
emoji: ♟️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Sabina Chess Backend

This is the Django backend for the Sabina Chess application, deployed on Hugging Face Spaces.

## Features
- User Authentication (JWT)
- Profile Management
- WebSocket support (optional configuration)

## Deployment
This project is automatically deployed to Hugging Face Spaces via GitHub Actions.

### Manual Setup
If you need to run this locally using Docker:
```bash
docker build -t sabina-chess .
docker run -p 7860:7860 sabina-chess
```
