FROM python:3.14-slim

#ffmpeg installieren
RUN apt-get update && apt-get install -y ffmpeg

#Bot-code kopieren
COPY . /app
WORKDIR /app

#Bot starten
CMD ["python", "bot.py"]
