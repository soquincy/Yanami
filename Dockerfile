# Dockerfile: A simple Dockerfile to containerize the bot. It uses the official Python 3.13 slim image, installs ffmpeg and nodejs for any future features that might require them, and then installs the Python dependencies from requirements.txt. Finally, it copies the bot code into the container and sets the command to run the bot.

# Well, really its for the folks that know Docker and either want to run the bot in a container or want to deploy it to a service. Much easier if you use this in Railway or Fly.io or something like that, since you can just tell it to build the Dockerfile and it will handle the rest.

# If you're running it locally, you can still use this Dockerfile if you want, but it's not strictly necessary. You can just run the bot with Python if you have the dependencies installed. To each their own.

FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]