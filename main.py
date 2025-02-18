import os
import sys
import logging
import discord
from discord.ext import commands
import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ログ設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler('bot.log', encoding='utf-8')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# CSVデータのパス
bot.gacha_data_path = 'data/gacha_data.csv'

# タイムゾーンはJST
JST = pytz.timezone('Asia/Tokyo')
scheduler = AsyncIOScheduler(timezone=JST)

# ユーザーデータ
bot.user_points = {}      # {user_id: int} ユーザーポイント
bot.user_cards = {}       # {user_id: [card_no, ...]} ユーザーが取得したカード
bot.daily_auto_points = 1 # 毎日00:00に自動付与されるポイント数(初期値1)
bot.last_gacha_usage = {} # クールダウン管理用

def ensure_user_points(user_id):
    # ユーザーが未登録の場合、初期値15ptで登録
    if user_id not in bot.user_points:
        bot.user_points[user_id] = 15

bot.ensure_user_points = ensure_user_points

def add_daily_points():
    # 毎日00:00に全ユーザーに bot.daily_auto_points 分ポイント付与（最大15ptまで）
    for user_id, points in bot.user_points.items():
        if points < 15:
            new_points = min(15, points + bot.daily_auto_points)
            bot.user_points[user_id] = new_points
    logger.info(f"Daily {bot.daily_auto_points} point(s) added to all users at JST 00:00")

scheduler.add_job(add_daily_points, 'cron', hour=0, minute=0)

# 全アプリケーションコマンドの使用とパラメータ詳細をログ出力
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.application_command:
        command_name = interaction.data.get("name", "Unknown")
        user = interaction.user
        options = interaction.data.get("options", [])
        param_list = []
        for opt in options:
            if "resolved" in opt:
                resolved = opt["resolved"]
                param_value = None
                if isinstance(resolved, dict):
                    if "username" in resolved and "discriminator" in resolved:
                        param_value = f"{resolved['username']}#{resolved['discriminator']}"
                    else:
                        param_value = opt.get("value")
                else:
                    param_value = opt.get("value")
            else:
                param_value = opt.get("value")
            param_list.append(f"{opt['name']}={param_value}")
        params_str = ", ".join(param_list) if param_list else "None"
        logger.info(f"User {user.name} (ID: {user.id}) used command /{command_name} with parameters: {params_str}")

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}!')
    # Cogの読み込み
    await bot.load_extension("cogs.gacha")
    await bot.load_extension("cogs.admin")
    await bot.tree.sync()
    scheduler.start()
    logger.info("Scheduler started.")

TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable not set")

bot.run(TOKEN)
