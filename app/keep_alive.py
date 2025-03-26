import os
import threading
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

@app.route('/health')
def health_check():
    return "OK", 200

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    """
    Flaskサーバーをバックグラウンドでデーモンとして起動
    """
    server = threading.Thread(target=run)
    server.daemon = True
    server.start()
