import os
import json
import random
import asyncio
import datetime
import logging
from threading import Thread
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands
from flask import Flask
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import valo_api  # Valorant API ライブラリをインポート

# -------------------------------
# ログの設定
logging.basicConfig(level=logging.INFO)

# -------------------------------
# Valorant API の設定
valo_api.set_api_key(os.getenv("VALO_API_KEY"))

# -------------------------------
# Valorant ランク情報取得関数
def get_valorant_rank(region, name, tag):
    """
    Valorantのランク情報を取得する関数
    
    Args:
        region (str): リージョン（例: 'ap', 'na', 'eu'）
        name (str): Valorantユーザー名
        tag (str): Valorantタグ
        
    Returns:
        dict or None: ランク情報を含む辞書。エラー時はNone
    """
    if not name or not tag:
        logging.warning(f"Valorantユーザー名またはタグが空です: name='{name}', tag='{tag}'")
        return None
        
    try:
        logging.info(f"Valorantランク情報取得開始: region={region}, name={name}, tag={tag}")
        
        # バージョンを 'v2' として指定
        mmr_data = valo_api.get_mmr_details_by_name("v2", region, name, tag)
        
        # mmr_dataが存在するか確認
        if not mmr_data:
            logging.warning(f"MMRデータが取得できませんでした: region={region}, name={name}, tag={tag}")
            return None
            
        # current_dataが存在するか確認
        if not hasattr(mmr_data, 'current_data') or not mmr_data.current_data:
            logging.warning(f"current_dataがありません: region={region}, name={name}, tag={tag}")
            return None
            
        # highest_rankが存在するか確認
        if not hasattr(mmr_data, 'highest_rank') or not mmr_data.highest_rank:
            logging.warning(f"highest_rankがありません: region={region}, name={name}, tag={tag}")
            highest_rank = "Unknown"
            highest_rank_season = "Unknown"
        else:
            highest_rank = mmr_data.highest_rank.patched_tier
            highest_rank_season = mmr_data.highest_rank.season
        
        # 現在のランク情報
        current_rank = mmr_data.current_data.currenttierpatched
        tier_ranking = mmr_data.current_data.ranking_in_tier
        mmr_change = mmr_data.current_data.mmr_change_to_last_game
        elo = mmr_data.current_data.elo
        
        result = {
            "current_rank": current_rank,
            "tier_ranking": tier_ranking,
            "mmr_change": mmr_change,
            "elo": elo,
            "highest_rank": highest_rank,
            "highest_rank_season": highest_rank_season,
            "raw_data": mmr_data
        }
        
        logging.info(f"Valorantランク情報取得成功: name={name}, rank={current_rank}")
        return result
        
    except Exception as e:
        logging.error(f"Valorantランク情報取得エラー: {str(e)}", exc_info=True)
        # エラーの詳細をログに記録
        import traceback
        logging.error(traceback.format_exc())
        return None

# -------------------------------
# Googleスプレッドシートの認証設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials_info = json.loads(os.getenv("CREDENTIALS_JSON"))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
gc = gspread.authorize(credentials)
sheet = gc.open("Accounts").sheet1  # スプレッドシート名を指定

# -------------------------------
# Discord Bot の設定
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True       # メンバー情報取得用
intents.voice_states = True  # ボイス関連イベント用
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree  # スラッシュコマンド管理用

# -------------------------------
# タイムゾーンの設定（東京）
TOKYO_TZ = ZoneInfo("Asia/Tokyo")

# -------------------------------
# アカウント管理用変数
# borrowed_accounts: {user_id: {"account": account_data, "task": task, "guild_id": guild_id, "channel_id": channel_id}}
borrowed_accounts = {}
user_status = {}

# -------------------------------
# カスタムモーダルクラス（アカウント登録用）
class AccountRegisterModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="アカウント登録フォーム")
        self.add_item(discord.ui.TextInput(
            label="Name",
            placeholder="例: user",
            custom_id="account-name",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="ID",
            placeholder="例: neonotp",
            custom_id="account-id",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Password",
            placeholder="例: ******",
            custom_id="account-password",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Valorant Username",
            placeholder="例: neonotp",
            custom_id="valorant-username",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Valorant Tag",
            placeholder="例: judge",
            custom_id="valorant-tag",
            required=True
        ))

    async def on_submit(self, interaction: discord.Interaction):
        name = self.children[0].value
        account_id = self.children[1].value
        password = self.children[2].value
        val_username = self.children[3].value
        val_tag = self.children[4].value
        
        # 入力チェック
        if not val_username or not val_tag:
            await interaction.response.send_message(
                "Valorantのユーザーネームとタグは必須です。",
                ephemeral=True
            )
            return
        
        # Valorantのランク情報を取得
        logging.info(f"アカウント登録: Valorantランク情報取得試行 - {val_username}#{val_tag}")
        rank_info = get_valorant_rank("ap", val_username, val_tag)
        rank = "Unknown"
        
        if rank_info:
            rank = rank_info["current_rank"]
            logging.info(f"アカウント登録: ランク情報取得成功 - {val_username}#{val_tag}, Rank: {rank}")
        else:
            logging.warning(f"アカウント登録: ランク情報取得失敗 - {val_username}#{val_tag}")
        
        try:
            # スプレッドシートのヘッダー確認（必要に応じて）
            headers = sheet.row_values(1)
            logging.info(f"スプレッドシートのヘッダー: {headers}")
            
            # 既存の列数を確認
            header_count = len(headers)
            
            # 最低限必要な列数
            min_required_cols = 7  # name, id, password, rank, status, val_username, val_tag
            
            # 必要に応じてヘッダーを追加
            if header_count < min_required_cols:
                # 必要な列名
                required_headers = ["name", "id", "password", "rank", "status", "val_username", "val_tag"]
                missing_headers = required_headers[header_count:]
                
                # スプレッドシートに新しいヘッダーを追加（例外処理付き）
                for i, header in enumerate(missing_headers, start=header_count+1):
                    try:
                        sheet.update_cell(1, i, header)
                        logging.info(f"スプレッドシートにヘッダー '{header}' を追加しました")
                    except Exception as e:
                        logging.error(f"ヘッダー追加エラー '{header}': {e}")
            
            # スプレッドシートに保存 [name, id, password, rank, status, val_username, val_tag]
            row_data = [name, account_id, password, rank, "available", val_username, val_tag]
            
            await asyncio.get_event_loop().run_in_executor(
                None, sheet.append_row, row_data
            )
            logging.info(f"アカウント登録成功: {name}, Valorant: {val_username}#{val_tag}")
            
            # 応答メッセージの作成
            response_message = f"アカウント **{name}** を登録しました！\n"
            
            if rank != "Unknown":
                response_message += f"自動取得したランク: **{rank}**"
            else:
                response_message += "ランク情報の自動取得ができませんでした。"
            
            if rank_info:
                response_message += (
                    f"\n\n**Valorant詳細情報:**\n"
                    f"**ティア内ランキング:** {rank_info['tier_ranking']}\n"
                    f"**最後のゲームでのMMR変化:** {rank_info['mmr_change']}\n"
                    f"**ELO:** {rank_info['elo']}\n"
                    f"**過去最高ランク:** {rank_info['highest_rank']} (シーズン: {rank_info['highest_rank_season']})"
                )
                
            await interaction.response.send_message(
                response_message,
                ephemeral=True
            )
            
        except Exception as e:
            error_msg = f"スプレッドシートへの書き込みエラー: {str(e)}"
            logging.error(error_msg, exc_info=True)
            import traceback
            logging.error(traceback.format_exc())
            await interaction.response.send_message(
                f"アカウントの登録に失敗しました。\nエラー: {str(e)}",
                ephemeral=True
            )
            return

# /register コマンド
@tree.command(name="register", description="新規アカウントを登録します")
async def register(interaction: discord.Interaction):
    await interaction.response.send_modal(AccountRegisterModal())

# -------------------------------
# 自動返却タスク（5時間後に自動返却）
async def auto_return_account(user_id: int, account: dict, guild_id: int, channel_id: int):
    await asyncio.sleep(5 * 60 * 60)  # 5時間待機
    try:
        logging.info(f"自動返却処理開始: User ID={user_id}, Account={account['name']}")
        await asyncio.get_event_loop().run_in_executor(
            None, sheet.update_cell, account["row"], 5, "available"
        )
        borrowed_accounts.pop(user_id, None)
        user_status.pop(user_id, None)
        guild = bot.get_guild(guild_id)
        if guild is None:
            logging.error(f"Guild ID {guild_id} が見つかりません。")
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            logging.error(f"Channel ID {channel_id} がGuild ID {guild_id}内に見つかりません。")
            return
        user = guild.get_member(user_id)
        if user is None:
            logging.error(f"User ID {user_id} がGuild ID {guild_id}内に見つかりません。")
            return

        await channel.send(
            f"{user.mention} の **{account['name']}** に自動返却処理を行いました。"
        )
        logging.info(f"自動返却処理完了: User ID={user_id}, Account={account['name']}")
    except Exception as e:
        logging.error(f"自動返却中にエラーが発生しました: {e}")

# -------------------------------
# /use_account コマンド（アカウント借用）
@tree.command(name="use_account", description="アカウントを借りる")
async def use_account(interaction: discord.Interaction):
    if interaction.user.id in user_status:
        await interaction.response.send_message(
            "すでにアカウントを借りています。返却してください。",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        accounts = await asyncio.get_event_loop().run_in_executor(None, sheet.get_all_records)
    except Exception as e:
        logging.error(f"スプレッドシートからデータ取得中にエラーが発生しました: {e}")
        await interaction.followup.send(
            "スプレッドシートからデータを取得できませんでした。後でもう一度試してください。",
            ephemeral=True
        )
        return

    available_accounts = [
        {**acc, "row": index + 2}
        for index, acc in enumerate(accounts)
        if acc["status"] == "available"
    ]

    if not available_accounts:
        await interaction.followup.send(
            "利用可能なアカウントがありません。",
            ephemeral=True
        )
        return

    options = [
        discord.SelectOption(label=f"{acc['name']} ({acc['rank']})", value=acc["name"])
        for acc in available_accounts
    ]

    class AccountDropdown(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="アカウントを選択してください", options=options)

        async def callback(self, interaction: discord.Interaction):
            # 応答を遅延させる
            await interaction.response.defer(ephemeral=True)
            
            selected_account = next(
                acc for acc in available_accounts if acc["name"] == self.values[0]
            )
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, sheet.update_cell, selected_account["row"], 5, "borrowed"
                )
            except Exception as e:
                logging.error(f"スプレッドシートの状態更新中にエラーが発生しました: {e}")
                await interaction.followup.send(
                    "アカウントの状態を更新できませんでした。後でもう一度試してください。",
                    ephemeral=True
                )
                return

            user_status[interaction.user.id] = True
            borrowed_accounts[interaction.user.id] = {
                "account": selected_account,
                "task": None,
                "guild_id": interaction.guild.id,
                "channel_id": interaction.channel.id
            }

            guild_id = interaction.guild.id if interaction.guild else None
            channel_id = interaction.channel.id if interaction.channel else None
            if guild_id is None or channel_id is None:
                await interaction.followup.send(
                    "サーバー情報の取得に失敗しました。管理者に連絡してください。",
                    ephemeral=True
                )
                return

            task = asyncio.create_task(auto_return_account(interaction.user.id, selected_account, guild_id, channel_id))
            borrowed_accounts[interaction.user.id]["task"] = task

            return_time = datetime.datetime.now(TOKYO_TZ) + datetime.timedelta(hours=5)
            return_time_str = return_time.strftime('%Y-%m-%d %H:%M:%S %Z')
            
            # Valorantのより詳細なランク情報を取得
            rank_info = None
            rank_update_success = False
            
            if "val_username" in selected_account and "val_tag" in selected_account:
                val_username = selected_account.get("val_username")
                val_tag = selected_account.get("val_tag")
                
                if val_username and val_tag:
                    logging.info(f"アカウント借用: Valorantランク情報取得試行 - {val_username}#{val_tag}")
                    
                    try:
                        rank_info = get_valorant_rank("ap", val_username, val_tag)
                        
                        # 取得に成功した場合はスプレッドシートのランク情報を更新
                        if rank_info:
                            logging.info(f"アカウント借用: ランク情報取得成功 - {val_username}#{val_tag}, Rank: {rank_info['current_rank']}")
                            
                            try:
                                # スプレッドシートのランク列（4列目）を更新
                                await asyncio.get_event_loop().run_in_executor(
                                    None, sheet.update_cell, selected_account["row"], 4, rank_info["current_rank"]
                                )
                                logging.info(f"アカウント借用: スプレッドシートのランク更新成功 - row: {selected_account['row']}, rank: {rank_info['current_rank']}")
                                
                                # メモリ上のアカウント情報も更新
                                selected_account["rank"] = rank_info["current_rank"]
                                rank_update_success = True
                            except Exception as e:
                                logging.error(f"アカウント借用: スプレッドシートのランク更新エラー - {str(e)}", exc_info=True)
                                import traceback
                                logging.error(traceback.format_exc())
                        else:
                            logging.warning(f"アカウント借用: ランク情報取得失敗 - {val_username}#{val_tag}")
                    except Exception as e:
                        logging.error(f"Valorantランク情報更新エラー: {str(e)}", exc_info=True)
                        import traceback
                        logging.error(traceback.format_exc())
                else:
                    logging.warning(f"アカウント借用: ユーザー名またはタグが空 - username: '{val_username}', tag: '{val_tag}'")
            else:
                logging.warning("アカウント借用: Valorant情報なし - val_usernameまたはval_tagがアカウント情報に存在しません")
                logging.debug(f"アカウント情報キー: {list(selected_account.keys())}")
            
            # アカウント情報の表示
            account_details = (
                f"**アカウント情報:**\n"
                f"**Name:** {selected_account['name']}\n"
                f"**ID:** {selected_account['id']}\n"
                f"**Password:** {selected_account['password']}\n"
                f"**Rank:** {selected_account['rank']}"
            )
            
            if rank_update_success:
                account_details += " (自動更新済み)"
            
            # Valorantユーザー情報を追加
            if "val_username" in selected_account and "val_tag" in selected_account:
                account_details += f"\n**Valorant:** {selected_account['val_username']}#{selected_account['val_tag']}"
            
            # Valorantの詳細情報がある場合は追加
            if rank_info:
                account_details += (
                    f"\n\n**Valorant詳細情報:**\n"
                    f"**現在のランク:** {rank_info['current_rank']}\n"
                    f"**ティア内ランキング:** {rank_info['tier_ranking']}\n"
                    f"**最後のゲームでのMMR変化:** {rank_info['mmr_change']}\n"
                    f"**ELO:** {rank_info['elo']}\n"
                    f"**過去最高ランク:** {rank_info['highest_rank']} (シーズン: {rank_info['highest_rank_season']})\n"
                )
            elif "val_username" in selected_account and "val_tag" in selected_account:
                account_details += "\n\n**注意:** Valorantの詳細情報を取得できませんでした。"
            
            account_details += f"\n**返却期限:** {return_time_str}\n"
            
            await interaction.followup.send(account_details, ephemeral=True)
            await interaction.channel.send(
                f"{interaction.user.mention} が **{selected_account['name']}** を借りました！"
            )

    view = discord.ui.View()
    view.add_item(AccountDropdown())
    await interaction.followup.send("アカウントを選択してください:", view=view, ephemeral=True)

# -------------------------------
# /update_ranks コマンド（すべてのアカウントのランク情報を一括更新）
@tree.command(name="update_ranks", description="すべてのアカウントのランク情報を一括更新します")
async def update_ranks(interaction: discord.Interaction, status: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "このコマンドは管理者のみ使用できます。",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    
    try:
        accounts = await asyncio.get_event_loop().run_in_executor(None, sheet.get_all_records)
    except Exception as e:
        logging.error(f"スプレッドシートからデータ取得中にエラーが発生しました: {e}")
        await interaction.followup.send(
            "スプレッドシートからデータを取得できませんでした。後でもう一度試してください。",
            ephemeral=True
        )
        return
    
    # ステータスパラメータが指定されている場合はフィルタリング
    if status:
        filtered_accounts = [
            {**acc, "row": index + 2}
            for index, acc in enumerate(accounts)
            if acc["status"].lower() == status.lower()
        ]
        
        if not filtered_accounts:
            await interaction.followup.send(
                f"ステータスが '{status}' のアカウントは見つかりませんでした。",
                ephemeral=True
            )
            return
        target_accounts = filtered_accounts
    else:
        # ステータスが指定されていない場合はすべてのアカウント
        target_accounts = [{**acc, "row": index + 2} for index, acc in enumerate(accounts)]
    
    if not target_accounts:
        await interaction.followup.send("更新対象のアカウントがありません。", ephemeral=True)
        return
    
    await interaction.followup.send(
        f"{len(target_accounts)}件のアカウントのランク情報を更新しています...",
        ephemeral=True
    )
    
    success_count = 0
    fail_count = 0
    no_val_info_count = 0
    
    # 処理状況表示のためのプログレスメッセージ
    progress_message = await interaction.followup.send(
        "0% 完了 (0/{})".format(len(target_accounts)),
        ephemeral=True
    )
    
    updated_accounts = []
    
    for i, account in enumerate(target_accounts):
        # 10%完了ごとに進捗を更新
        if (i % max(1, len(target_accounts) // 10)) == 0 or i == len(target_accounts) - 1:
            progress_percent = int((i / len(target_accounts)) * 100)
            try:
                await progress_message.edit(content=f"{progress_percent}% 完了 ({i}/{len(target_accounts)})")
            except:
                pass
        
        if "val_username" not in account or "val_tag" not in account or not account.get("val_username") or not account.get("val_tag"):
            no_val_info_count += 1
            continue
        
        val_username = account.get("val_username")
        val_tag = account.get("val_tag")
        
        logging.info(f"一括ランク更新: {val_username}#{val_tag} の情報取得中...")
        
        try:
            rank_info = get_valorant_rank("ap", val_username, val_tag)
            
            if rank_info:
                old_rank = account.get("rank", "Unknown")
                new_rank = rank_info["current_rank"]
                
                # ランクが変わった場合のみスプレッドシートを更新（APIリクエスト削減のため）
                if old_rank != new_rank:
                    await asyncio.get_event_loop().run_in_executor(
                        None, sheet.update_cell, account["row"], 4, new_rank
                    )
                    logging.info(f"ランク更新: {val_username}#{val_tag} - {old_rank} -> {new_rank}")
                    account["rank"] = new_rank
                    updated_accounts.append({
                        "name": account["name"],
                        "old_rank": old_rank,
                        "new_rank": new_rank
                    })
                
                success_count += 1
            else:
                fail_count += 1
                logging.warning(f"一括ランク更新: {val_username}#{val_tag} のランク情報取得に失敗しました")
        except Exception as e:
            fail_count += 1
            logging.error(f"一括ランク更新エラー ({val_username}#{val_tag}): {str(e)}", exc_info=True)
        
        # APIレート制限対策のための短い待機
        await asyncio.sleep(0.5)
    
    # 結果サマリー
    summary = (
        f"**ランク更新完了**\n"
        f"- 対象アカウント: {len(target_accounts)}件\n"
        f"- 成功: {success_count}件\n"
        f"- 失敗: {fail_count}件\n"
        f"- Valorant情報なし: {no_val_info_count}件\n"
    )
    
    # ランクが変更されたアカウントがある場合はリストを表示
    if updated_accounts:
        summary += "\n**ランクが変更されたアカウント:**\n"
        for acc in updated_accounts:
            summary += f"- {acc['name']}: {acc['old_rank']} → {acc['new_rank']}\n"
    
    await interaction.followup.send(summary, ephemeral=True)
    
    # チャンネルにも通知（ランクが更新されたアカウントがある場合のみ）
    if updated_accounts:
        channel_message = f"**{interaction.user.display_name} がアカウントのランク情報を更新しました**\n"
        channel_message += f"更新されたアカウント: {len(updated_accounts)}件\n"
        for acc in updated_accounts[:10]:  # 長すぎる場合は最初の10件のみ表示
            channel_message += f"- {acc['name']}: {acc['old_rank']} → {acc['new_rank']}\n"
        
        if len(updated_accounts) > 10:
            channel_message += f"...ほか {len(updated_accounts) - 10}件\n"
        
        await interaction.channel.send(channel_message)

# -------------------------------
# /return_account コマンド（アカウント返却）
@tree.command(name="return_account", description="アカウントを返却する")
async def return_account(interaction: discord.Interaction):
    if interaction.user.id not in borrowed_accounts:
        await interaction.response.send_message("返却するアカウントがありません。", ephemeral=True)
        return

    account_info = borrowed_accounts.get(interaction.user.id)
    account = account_info["account"]
    task = account_info["task"]
    guild_id = account_info.get("guild_id")
    channel_id = account_info.get("channel_id")

    # 状態チェック（不整合の場合はリセット）
    if not account or sheet.cell(account["row"], 5).value != "borrowed":
        borrowed_accounts.pop(interaction.user.id, None)
        user_status.pop(interaction.user.id, None)
        if task:
            task.cancel()
        await interaction.response.send_message(
            "アカウントの借用状態が不整合でしたが、自動的にリセットしました。再度借用してください。",
            ephemeral=True
        )
        return

    if task:
        task.cancel()

    class RankUpdateModal(discord.ui.Modal):
        def __init__(self):
            super().__init__(title="ランク更新")
            
            # ランクの自動取得を試みる
            auto_rank = account["rank"]
            rank_info = None
            rank_fetch_success = False
            
            if "val_username" in account and "val_tag" in account:
                val_username = account.get("val_username")
                val_tag = account.get("val_tag")
                
                if val_username and val_tag:
                    logging.info(f"アカウント返却: Valorantランク情報取得試行 - {val_username}#{val_tag}")
                    
                    try:
                        rank_info = get_valorant_rank("ap", val_username, val_tag)
                        if rank_info:
                            auto_rank = rank_info["current_rank"]
                            rank_fetch_success = True
                            logging.info(f"アカウント返却: ランク情報取得成功 - {val_username}#{val_tag}, Rank: {auto_rank}")
                        else:
                            logging.warning(f"アカウント返却: ランク情報取得失敗 - {val_username}#{val_tag}")
                    except Exception as e:
                        logging.error(f"返却時のValorantランク情報取得エラー: {str(e)}", exc_info=True)
                        import traceback
                        logging.error(traceback.format_exc())
                else:
                    logging.warning(f"アカウント返却: ユーザー名またはタグが空 - username: '{val_username}', tag: '{val_tag}'")
            else:
                logging.warning("アカウント返却: Valorant情報なし - val_usernameまたはval_tagがアカウント情報に存在しません")
                logging.debug(f"アカウント情報キー: {list(account.keys())}")
            
            # 手動入力欄にデフォルト値として自動取得したランクを設定
            self.add_item(discord.ui.TextInput(
                label="新しいランクを入力",
                placeholder="変更がなければ同じランクを入力してください",
                default=auto_rank,
                custom_id="new-rank",
                required=True
            ))
            
            # 取得したランク情報と自動取得成功フラグを保存
            self.rank_info = rank_info
            self.auto_rank = auto_rank
            self.rank_fetch_success = rank_fetch_success

        async def on_submit(self, interaction: discord.Interaction):
            new_rank = self.children[0].value
            rank_updated = False
            
            # 入力値のチェック
            if not new_rank:
                new_rank = account["rank"]
                logging.warning("アカウント返却: 新しいランクが空のため、現在のランクを使用")
            
            # ランク情報に変更があれば更新
            if new_rank != account["rank"]:
                logging.info(f"アカウント返却: ランク更新 - 古い: {account['rank']}, 新しい: {new_rank}")
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, sheet.update_cell, account["row"], 4, new_rank
                    )
                    logging.info(f"アカウント返却: スプレッドシートのランク更新成功 - row: {account['row']}, rank: {new_rank}")
                    rank_updated = True
                except Exception as e:
                    error_msg = f"スプレッドシートのランクセル更新中にエラーが発生しました: {str(e)}"
                    logging.error(error_msg, exc_info=True)
                    import traceback
                    logging.error(traceback.format_exc())
                    await interaction.response.send_message(
                        f"ランクの更新に失敗しました。後でもう一度試してください。\nエラー: {str(e)}",
                        ephemeral=True
                    )
                    return
            
            # アカウント状態を "available" に更新
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, sheet.update_cell, account["row"], 5, "available"
                )
                logging.info(f"アカウント返却: ステータス更新成功 - row: {account['row']}, status: available")
            except Exception as e:
                error_msg = f"スプレッドシートの状態更新中にエラーが発生しました: {str(e)}"
                logging.error(error_msg, exc_info=True)
                import traceback
                logging.error(traceback.format_exc())
                await interaction.response.send_message(
                    f"アカウントの状態を更新できませんでした。後でもう一度試してください。\nエラー: {str(e)}",
                    ephemeral=True
                )
                return

            # ユーザーの借用状態をクリア
            borrowed_accounts.pop(interaction.user.id, None)
            user_status.pop(interaction.user.id, None)
            logging.info(f"アカウント返却: ユーザーID {interaction.user.id} の借用状態をクリア")
            
            # メッセージ送信のためにギルド、チャンネル、ユーザー情報を取得
            guild = bot.get_guild(guild_id)
            channel = None
            user = None
            
            if guild is None:
                logging.error(f"Guild ID {guild_id} が見つかりません。")
            else:
                channel = guild.get_channel(channel_id)
                if channel is None:
                    logging.error(f"Channel ID {channel_id} がGuild ID {guild_id}内に見つかりません。")
                
                user = guild.get_member(interaction.user.id)
                if user is None:
                    logging.error(f"User ID {interaction.user.id} がGuild ID {guild_id}内に見つかりません。")

            # 返却完了メッセージの作成
            rank_status = ""
            if self.rank_fetch_success:
                rank_status = " (自動取得)"
            elif rank_updated:
                rank_status = " (手動更新)"
                
            reply_message = f"アカウント **{account['name']}** を返却しました。\n**新しいランク:** {new_rank}{rank_status}"
            channel_message = f"{user.mention if user else '不明なユーザー'} が **{account['name']}** を返却しました！\n**更新後のランク:** {new_rank}{rank_status}"
            
            # Valorantの詳細情報がある場合は追加
            if self.rank_info:
                rank_details = (
                    f"\n\n**Valorant詳細情報:**\n"
                    f"**ティア内ランキング:** {self.rank_info['tier_ranking']}\n"
                    f"**最後のゲームでのMMR変化:** {self.rank_info['mmr_change']}\n"
                    f"**ELO:** {self.rank_info['elo']}\n"
                    f"**過去最高ランク:** {self.rank_info['highest_rank']} (シーズン: {self.rank_info['highest_rank_season']})"
                )
                reply_message += rank_details
                channel_message += rank_details

            # ユーザーに返却完了メッセージを送信
            await interaction.response.send_message(
                reply_message,
                ephemeral=True
            )
            
            # チャンネルが存在すれば返却通知を送信
            if channel:
                await channel.send(channel_message)
            else:
                logging.warning("アカウント返却: チャンネルが見つからないため、返却通知を送信できません")

    modal = RankUpdateModal()
    await interaction.response.send_modal(modal)

# ------------------------------
# /remove_comment コマンド（コメント削除）
@tree.command(name="remove_comment", description="コードブロック、画像、ファイルを除くコメントを削除します。")
async def remove_comment(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
        return

    await interaction.response.defer()

    channel = interaction.channel
    now = datetime.datetime.now(datetime.timezone.utc)
    bulk_deletable_messages = []
    async_deletable_messages = []

    async for message in channel.history(limit=100):
        if not message.attachments and "```" not in message.content and not message.embeds:
            if (now - message.created_at).days <= 14:
                bulk_deletable_messages.append(message)
            else:
                async_deletable_messages.append(message)

    bulk_deleted_count = 0
    if bulk_deletable_messages:
        try:
            await channel.delete_messages(bulk_deletable_messages)
            bulk_deleted_count = len(bulk_deletable_messages)
        except Exception as e:
            logging.error(f"一括削除中にエラーが発生しました: {e}")

    async_deleted_count = 0
    for message in async_deletable_messages:
        try:
            await message.delete()
            async_deleted_count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logging.error(f"個別削除中にエラーが発生しました: {e}")

    total_deleted = bulk_deleted_count + async_deleted_count
    await interaction.followup.send(
        f"削除が完了しました！\n- 一括削除: {bulk_deleted_count} 件\n- 個別削除: {async_deleted_count} 件\n- 合計: {total_deleted} 件"
    )

# -------------------------------
# /reset_borrowed コマンド（管理者専用：借用状態の手動リセット）
@tree.command(name="reset_borrowed", description="借用状態を手動でリセットします（管理者専用）")
async def reset_borrowed(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
        return

    try:
        user_id_int = int(user_id)
        if user_id_int in borrowed_accounts:
            account_info = borrowed_accounts.pop(user_id_int)
            user_status.pop(user_id_int, None)
            task = account_info.get("task")
            if task:
                task.cancel()
            await interaction.response.send_message(f"ユーザーID {user_id} の借用状態をリセットしました。", ephemeral=True)
        else:
            await interaction.response.send_message(f"ユーザーID {user_id} は借用状態ではありません。", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("正しいユーザーIDを入力してください。", ephemeral=True)

# -------------------------------
# 以下、スマスロカバネリ覚醒ゾーン再現用 /kabaneri コマンドの強化部分
# ※画像ファイルは app/kabaneri 内に配置している前提

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

@tree.command(name="kabaneri", description="六根清浄！")
async def kabaneri(interaction: discord.Interaction):
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
        embed = discord.Embed(title="パチンコ・パチスロは適度に楽しむ遊びです", description="のめり込みに注意しましょう。")
        embed.add_field(name="リール結果", value=result_text, inline=False)
        await interaction.followup.send(embed=embed)

# -------------------------------
# Flaskアプリケーション（ヘルスチェック用）
app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# Flaskサーバーをバックグラウンドで起動
thread = Thread(target=run_flask)
thread.daemon = True
thread.start()

# Bot準備完了時の処理
@bot.event
async def on_ready():
    await tree.sync()
    logging.info(f"Logged in as {bot.user}")

# -------------------------------
# Bot の起動
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
