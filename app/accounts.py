import logging
import asyncio
import datetime
from zoneinfo import ZoneInfo

# タイムゾーンの設定（東京）
TOKYO_TZ = ZoneInfo("Asia/Tokyo")

# アカウント管理用変数
# borrowed_accounts: {user_id: {"account": account_data, "task": task, "guild_id": guild_id, "channel_id": channel_id}}
borrowed_accounts = {}
user_status = {}


# 自動返却タスク（5時間後に自動返却）
async def auto_return_account(user_id, account, guild_id, channel_id, bot, sheet_updater):
    """
    指定時間後にアカウントを自動的に返却するタスク
    
    Args:
        user_id (int): ユーザーID
        account (dict): アカウント情報
        guild_id (int): サーバーID
        channel_id (int): チャンネルID
        bot: Discordボット
        sheet_updater: スプレッドシート更新用の関数
    """
    await asyncio.sleep(5 * 60 * 60)  # 5時間待機
    try:
        logging.info(f"自動返却処理開始: User ID={user_id}, Account={account['name']}")
        # スプレッドシートの状態を更新
        await sheet_updater(account["row"], 5, "available")
        
        # 借用情報をクリア
        borrowed_accounts.pop(user_id, None)
        user_status.pop(user_id, None)
        
        # サーバー、チャンネル、ユーザー情報を取得
        guild = bot.get_guild(guild_id)
        if guild is None:
            logging.error(f"Guild ID {guild_id} が見つかりません。")
            return
            
        channel = guild.get_channel(channel_id)
        if channel is None:
            logging.error(
                f"Channel ID {channel_id} がGuild ID {guild_id}内に見つかりません。"
            )
            return
            
        user = guild.get_member(user_id)
        if user is None:
            logging.error(
                f"User ID {user_id} がGuild ID {guild_id}内に見つかりません。"
            )
            return

        # 自動返却処理の埋め込みメッセージを作成して送信
        import discord
        embed = discord.Embed(
            title="自動返却通知",
            description=f"{user.mention} の **{account['name']}** に自動返却処理を行いました。",
            color=0xff0000  # 赤色
        )
        embed.set_footer(
            text=f"自動返却時刻: {datetime.datetime.now(TOKYO_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        await channel.send(embed=embed)
        
        logging.info(f"自動返却処理完了: User ID={user_id}, Account={account['name']}")
    except Exception as e:
        logging.error(f"自動返却中にエラーが発生しました: {e}")


def borrow_account(user_id, account, guild_id, channel_id):
    """
    ユーザーがアカウントを借りる処理
    
    Args:
        user_id (int): ユーザーID
        account (dict): アカウント情報
        guild_id (int): サーバーID
        channel_id (int): チャンネルID
        
    Returns:
        dict: アカウント借用情報
    """
    user_status[user_id] = True
    borrowed_info = {
        "account": account,
        "task": None,
        "guild_id": guild_id,
        "channel_id": channel_id
    }
    borrowed_accounts[user_id] = borrowed_info
    return borrowed_info


def get_borrowed_account(user_id):
    """
    ユーザーが借りているアカウント情報を取得
    
    Args:
        user_id (int): ユーザーID
        
    Returns:
        dict or None: アカウント借用情報、存在しない場合はNone
    """
    return borrowed_accounts.get(user_id)


def return_account(user_id):
    """
    ユーザーのアカウント借用状態をクリア
    
    Args:
        user_id (int): ユーザーID
        
    Returns:
        tuple: (task, account) タスクとアカウント情報のタプル
    """
    account_info = borrowed_accounts.pop(user_id, None)
    user_status.pop(user_id, None)
    
    if account_info:
        return account_info.get("task"), account_info.get("account")
    return None, None


def is_account_borrowed(user_id):
    """
    ユーザーがアカウントを借りているかチェック
    
    Args:
        user_id (int): ユーザーID
        
    Returns:
        bool: アカウントを借りている場合はTrue
    """
    return user_id in user_status


def get_return_time_str():
    """
    返却期限の文字列を取得
    
    Returns:
        str: 返却期限の文字列表現
    """
    return_time = datetime.datetime.now(TOKYO_TZ) + datetime.timedelta(hours=5)
    return return_time.strftime('%Y-%m-%d %H:%M:%S %Z') 