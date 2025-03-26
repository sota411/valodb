import os
import logging
import discord
from flask import Flask
from discord.ext import commands
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# 自作モジュールのインポート（絶対パスでインポート）
from app import valorant_api
from app import spreadsheet
from app.accounts import TOKYO_TZ
from app import commands as cmd
from app.keep_alive import keep_alive

# -------------------------------
# ログの設定
logging.basicConfig(level=logging.INFO)

# -------------------------------
# Valorant API の設定
valorant_api.setup_api()

# -------------------------------
# Googleスプレッドシートの初期化
sheet = spreadsheet.init_spreadsheet()

# -------------------------------
# Discord Bot の設定
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True       # メンバー情報取得用
intents.voice_states = True  # ボイス関連イベント用
bot = commands.Bot(command_prefix="/", intents=intents)

# -------------------------------
# Flask アプリケーション（ヘルスチェック用）
app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# Bot準備完了時の処理
@bot.event
async def on_ready():
    # スラッシュコマンドの登録
    tree = cmd.register_commands(
        bot, 
        sheet, 
        lambda row_data: spreadsheet.append_row(sheet, row_data),
        lambda row, col, value: spreadsheet.update_cell(sheet, row, col, value),
        lambda sht: spreadsheet.get_all_accounts(sht)
    )
    
    await tree.sync()
    logging.info(f"Logged in as {bot.user}")

# -------------------------------
# Bot の起動
def main():
    # Flaskサーバーをバックグラウンドで起動
    keep_alive()
    
    # Botを起動
    TOKEN = os.getenv("TOKEN")
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
