# VektorFlow BYOK Gateway

## One command to run
docker-compose up --build

## One URL to open
http://localhost:8080

## What you do
1. Click "LLM Setup Page"
2. Pick a provider (Groq, OpenAI, etc.)
3. Paste your API key
4. Click save

## Example API call
curl http://localhost:8080/v1/chat/completions -H "Authorization: Bearer YOUR_API_KEY" -H "Content-Type: application/json" -d '{"model": "groq/llama3-70b-8192", "messages": [{"role": "user", "content": "Hi"}]}'

## Stop server
docker-compose down

## Notes
- Keys in memory only (restart loses them)
- Voice input works in Chrome/Edge