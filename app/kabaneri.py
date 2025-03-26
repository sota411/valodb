import os
import random
import asyncio
import logging
import discord


# カバネリコマンド用定数
# 調整用パラメータ
# 各リールの停止までの待機時間（各リールごとに、GIFから結果画像へ切り替えるまでの秒数）
REEL_STOP_DELAYS = [0.7, 1.4, 2.1]
# リール結果表示後から特別演出開始までの待機時間（秒）
SPECIAL_EFFECT_DELAY = 0.1

# 基本ディレクトリの絶対パス（環境に合わせて変更）
BASE_DIR = os.path.join("app", "kabaneri")

# 各リールの初期状態は回転中の GIF 画像
REEL_GIFS = [
    os.path.join(BASE_DIR, "reel1_spin.gif"),
    os.path.join(BASE_DIR, "reel2_spin.gif"),
    os.path.join(BASE_DIR, "reel3_spin.gif")
]

# 各リールの停止時の画像（通常役とチャンス役）
REEL_FINAL_IMAGES = [
    {
        "normal": os.path.join(BASE_DIR, "reel_normal.png"),
        "chance": os.path.join(BASE_DIR, "reel1_chance.png")
    },
    {
        "normal": os.path.join(BASE_DIR, "reel_normal.png"),
        "chance": os.path.join(BASE_DIR, "reel2_chance.png")
    },
    {
        "normal": os.path.join(BASE_DIR, "reel_normal.png"),
        "chance": os.path.join(BASE_DIR, "reel3_chance.png")
    }
]

# 特別な当選演出用GIF
SPECIAL_WIN_GIF = os.path.join(BASE_DIR, "sp.gif")

# 再生する音声ファイル
ROKKON_AUDIO_FILE = os.path.join("app", "kabaneri", "rokkon.mp3")
FFMPEG_PATH = "ffmpeg"


# カバネリ機能コマンド
async def kabaneri_command(interaction):
    """
    カバネリコマンドの処理
    
    Args:
        interaction: Discordのインタラクション
    """
    # ボイスチャンネル参加の確認
    if interaction.user.voice is None or interaction.user.voice.channel is None:
        await interaction.response.send_message(
            "あなたはボイスチャンネルに参加していません。先に通話に参加してください。",
            ephemeral=True
        )
        return

    voice_channel = interaction.user.voice.channel

    # 初期応答（defer）
    await interaction.response.defer()

    # 各リールの回転中GIFを順次送信
    reel_messages = []
    for i in range(3):
        file = discord.File(REEL_GIFS[i], filename=f"reel{i+1}_spin.gif")
        embed = discord.Embed(title=f"Reel {i+1}", description="回転中...")
        embed.set_image(url=f"attachment://reel{i+1}_spin.gif")
        message = await interaction.followup.send(embed=embed, file=file)
        reel_messages.append(message)

    # 各リールの停止タイミング（weightを指定：chance:1, normal:4 => chanceが1/5の確率）
    final_results = [None, None, None]
    for i, delay in enumerate(REEL_STOP_DELAYS):
        await asyncio.sleep(delay)
        result = random.choices(["chance", "normal"], weights=[1, 4])[0]
        final_results[i] = result

        final_image_path = REEL_FINAL_IMAGES[i][result]
        file = discord.File(final_image_path, filename=os.path.basename(final_image_path))
        embed = discord.Embed(
            title=f"Reel {i+1}",
            description=f"{'チャンス' if result == 'chance' else '通常'}"
        )
        embed.set_image(url=f"attachment://{os.path.basename(final_image_path)}")
        try:
            await reel_messages[i].edit(embed=embed, attachments=[file])
        except discord.errors.HTTPException as e:
            logging.error(f"メッセージ編集中にエラーが発生しました: {e}")
            await interaction.followup.send(
                "リールの停止中にエラーが発生しました。管理者に連絡してください。",
                ephemeral=True
            )
            return

    # リール結果表示後、SPECIAL_EFFECT_DELAY秒待機してから特別演出に移行
    await asyncio.sleep(SPECIAL_EFFECT_DELAY)

    # 最終判定：いずれかのリールで chance が出た場合に特別演出
    if any(result == "chance" for result in final_results):
        file = discord.File(SPECIAL_WIN_GIF, filename=os.path.basename(SPECIAL_WIN_GIF))
        embed = discord.Embed(title="!!!六根清浄!!!", description="!!!貫け!!!鋼の魂!!!")
        embed.set_image(url=f"attachment://{os.path.basename(SPECIAL_WIN_GIF)}")
        await interaction.followup.send(embed=embed, file=file)

        try:
            if interaction.guild.voice_client:
                voice_client = interaction.guild.voice_client
                if voice_client.channel != voice_channel:
                    await voice_client.move_to(voice_channel)
            else:
                voice_client = await voice_channel.connect()
            if voice_client.is_playing():
                voice_client.stop()
            audio_source = discord.FFmpegPCMAudio(ROKKON_AUDIO_FILE, executable=FFMPEG_PATH)
            voice_client.play(audio_source)
            while voice_client.is_playing():
                await asyncio.sleep(1)
            await voice_client.disconnect()
        except Exception as e:
            logging.error(f"音声再生中にエラーが発生しました: {e}")
            await interaction.followup.send("音声の再生中にエラーが発生しました。", ephemeral=True)
    else:
        result_text = "\n".join([
            f"Reel {i+1}: {'チャンス' if result == 'chance' else '通常'}"
            for i, result in enumerate(final_results)
        ])
        embed = discord.Embed(title="パチンコ・パチスロは適度に楽しむ遊びです", 
                             description="のめり込みに注意しましょう。")
        embed.add_field(name="リール結果", value=result_text, inline=False)
        await interaction.followup.send(embed=embed) 