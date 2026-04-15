#!/usr/bin/env bash
set -e
echo ""
echo "==> Setting up AWS S3 Knowledge Base backend..."

cd "$(dirname "$0")/backend"

if [ ! -d ".venv" ]; then
  echo "    Creating Python virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo "✅  Setup complete!"
echo ""
echo "---------------------------------------------"
echo "NEXT STEPS:"
echo "  1. Open backend/env.txt, fill in:"
echo "       OPENAI_API_KEY"
echo "       AWS_ACCESS_KEY_ID"
echo "       AWS_SECRET_ACCESS_KEY"
echo "       AWS_REGION"
echo "       S3_BUCKET_NAME"
echo "     Then rename it to .env (or copy values into .env)"
echo ""
echo "  2. Start the backend:"
echo "       cd backend && source .venv/bin/activate && python3 main.py"
echo ""
echo "  3. Open frontend/index.html in your browser"
echo "---------------------------------------------"
