cloud-sql-proxy \
      --credentials-file=./april_ideas/backend/.critter-sa-key.json \
      wtroy-test-proj:us-central1:critter-sql --port=5433


python manage.py runserver

\033[1;33mTerminal 4 (optional) — RQ worker for video generation\033[0m
brew services start redis         # if not running
conda activate <your-env>
cd ~/Code/mine/april_ideas/backend
python manage.py rqworker high default low

ngrok http 8000