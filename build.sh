sudo docker build -t livekit-agent .
sudo docker run --env-file .env.local livekit-agent