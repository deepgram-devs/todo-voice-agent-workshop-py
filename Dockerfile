# Optional: run the app in a container instead of installing Python locally
# (see "No Python? No problem" in the README), or host a public demo instance
# where visitors paste their own API key. Not needed for the normal workshop
# path.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py agent.py todos.py verify.py ./
COPY public ./public
EXPOSE 3000
CMD ["python", "server.py"]
