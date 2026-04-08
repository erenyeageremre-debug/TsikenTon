from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Tsiken Ton 7/24 Nöbette!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()