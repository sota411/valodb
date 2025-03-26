import logging
import asyncio
import discord
from .valorant_api import get_valorant_rank


class AccountRegisterModal(discord.ui.Modal):
    """アカウント登録用のモーダル"""
    
    def __init__(self, sheet_append_row):
        """
        初期化
        
        Args:
            sheet_append_row: スプレッドシートに行を追加する関数
        """
        super().__init__(title="アカウント登録フォーム")
        self.sheet_append_row = sheet_append_row
        
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
        logging.info(
            f"アカウント登録: Valorantランク情報取得試行 - {val_username}#{val_tag}"
        )
        rank_info = get_valorant_rank("ap", val_username, val_tag)
        rank = "Unknown"
        
        if rank_info:
            rank = rank_info["current_rank"]
            logging.info(
                f"アカウント登録: ランク情報取得成功 - {val_username}#{val_tag}, Rank: {rank}"
            )
        else:
            logging.warning(
                f"アカウント登録: ランク情報取得失敗 - {val_username}#{val_tag}"
            )
        
        try:
            # スプレッドシートに保存 [name, id, password, rank, status, val_username, val_tag]
            row_data = [name, account_id, password, rank, "available", val_username, val_tag]
            
            result = await self.sheet_append_row(row_data)
            if not result:
                await interaction.response.send_message(
                    "データの保存に失敗しました。管理者に連絡してください。",
                    ephemeral=True
                )
                return
                
            logging.info(
                f"アカウント登録成功: {name}, Valorant: {val_username}#{val_tag}"
            )
            
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
                    f"**過去最高ランク:** {rank_info['highest_rank']} "
                    f"(シーズン: {rank_info['highest_rank_season']})"
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


class RankUpdateModal(discord.ui.Modal):
    """ランク更新用モーダル"""
    
    def __init__(self, account, sheet_update_cell, borrowed_accounts, user_status, 
                 guild_id, channel_id, bot):
        """
        初期化
        
        Args:
            account: アカウント情報
            sheet_update_cell: スプレッドシートのセルを更新する関数
            borrowed_accounts: 借りているアカウント管理辞書
            user_status: ユーザー状態管理辞書
            guild_id: サーバーID
            channel_id: チャンネルID
            bot: Discordボット
        """
        super().__init__(title="ランク更新")
        
        self.account = account
        self.sheet_update_cell = sheet_update_cell
        self.borrowed_accounts = borrowed_accounts
        self.user_status = user_status
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.bot = bot
        
        # ランクの自動取得を試みる
        auto_rank = account["rank"]
        self.rank_info = None
        self.rank_fetch_success = False
        
        if "val_username" in account and "val_tag" in account:
            val_username = account.get("val_username")
            val_tag = account.get("val_tag")
            
            if val_username and val_tag:
                logging.info(
                    f"アカウント返却: Valorantランク情報取得試行 - {val_username}#{val_tag}"
                )
                
                try:
                    self.rank_info = get_valorant_rank("ap", val_username, val_tag)
                    if self.rank_info:
                        auto_rank = self.rank_info["current_rank"]
                        self.rank_fetch_success = True
                        logging.info(
                            f"アカウント返却: ランク情報取得成功 - {val_username}#{val_tag}, "
                            f"Rank: {auto_rank}"
                        )
                    else:
                        logging.warning(
                            f"アカウント返却: ランク情報取得失敗 - {val_username}#{val_tag}"
                        )
                except Exception as e:
                    logging.error(f"返却時のValorantランク情報取得エラー: {str(e)}", 
                                  exc_info=True)
                    import traceback
                    logging.error(traceback.format_exc())
            else:
                logging.warning(
                    f"アカウント返却: ユーザー名またはタグが空 - username: '{val_username}', "
                    f"tag: '{val_tag}'"
                )
        else:
            logging.warning(
                "アカウント返却: Valorant情報なし - val_usernameまたはval_tagが"
                "アカウント情報に存在しません"
            )
            logging.debug(f"アカウント情報キー: {list(account.keys())}")
        
        # 手動入力欄にデフォルト値として自動取得したランクを設定
        self.add_item(discord.ui.TextInput(
            label="新しいランクを入力",
            placeholder="変更がなければ同じランクを入力してください",
            default=auto_rank,
            custom_id="new-rank",
            required=True
        ))
        
    async def on_submit(self, interaction: discord.Interaction):
        from .accounts import TOKYO_TZ
        import datetime
        
        new_rank = self.children[0].value
        rank_updated = False
        
        # 入力値のチェック
        if not new_rank:
            new_rank = self.account["rank"]
            logging.warning("アカウント返却: 新しいランクが空のため、現在のランクを使用")
        
        # ランク情報に変更があれば更新
        if new_rank != self.account["rank"]:
            logging.info(
                f"アカウント返却: ランク更新 - 古い: {self.account['rank']}, 新しい: {new_rank}"
            )
            try:
                result = await self.sheet_update_cell(
                    self.account["row"], 4, new_rank
                )
                if result:
                    logging.info(
                        f"アカウント返却: スプレッドシートのランク更新成功 - "
                        f"row: {self.account['row']}, rank: {new_rank}"
                    )
                    rank_updated = True
                else:
                    await interaction.response.send_message(
                        "ランクの更新に失敗しました。後でもう一度試してください。",
                        ephemeral=True
                    )
                    return
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
            result = await self.sheet_update_cell(
                self.account["row"], 5, "available"
            )
            if result:
                logging.info(
                    f"アカウント返却: ステータス更新成功 - row: {self.account['row']}, "
                    f"status: available"
                )
            else:
                await interaction.response.send_message(
                    "アカウントの状態を更新できませんでした。後でもう一度試してください。",
                    ephemeral=True
                )
                return
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
        user_id = interaction.user.id
        self.borrowed_accounts.pop(user_id, None)
        self.user_status.pop(user_id, None)
        logging.info(f"アカウント返却: ユーザーID {user_id} の借用状態をクリア")
        
        # メッセージ送信のためにギルド、チャンネル、ユーザー情報を取得
        guild = self.bot.get_guild(self.guild_id)
        channel = None
        user = None
        
        if guild is None:
            logging.error(f"Guild ID {self.guild_id} が見つかりません。")
        else:
            channel = guild.get_channel(self.channel_id)
            if channel is None:
                logging.error(
                    f"Channel ID {self.channel_id} がGuild ID {self.guild_id}内に"
                    f"見つかりません。"
                )
            
            user = guild.get_member(interaction.user.id)
            if user is None:
                logging.error(
                    f"User ID {interaction.user.id} がGuild ID {self.guild_id}内に"
                    f"見つかりません。"
                )

        # 返却完了メッセージの作成
        rank_status = ""
        if self.rank_fetch_success:
            rank_status = " (自動取得)"
        elif rank_updated:
            rank_status = " (手動更新)"
            
        reply_message = (
            f"アカウント **{self.account['name']}** を返却しました。\n"
            f"**新しいランク:** {new_rank}{rank_status}"
        )
        
        # Valorantの詳細情報がある場合は追加
        if self.rank_info:
            rank_details = (
                f"\n\n**Valorant詳細情報:**\n"
                f"**ティア内ランキング:** {self.rank_info['tier_ranking']}\n"
                f"**最後のゲームでのMMR変化:** {self.rank_info['mmr_change']}\n"
                f"**ELO:** {self.rank_info['elo']}\n"
                f"**過去最高ランク:** {self.rank_info['highest_rank']} "
                f"(シーズン: {self.rank_info['highest_rank_season']})"
            )
            reply_message += rank_details
        
        # ユーザーに返却完了メッセージを埋め込み形式で送信
        try:
            # 埋め込みメッセージを作成
            dm_embed = discord.Embed(
                title=f"アカウント返却完了: {self.account['name']}",
                description=f"アカウント **{self.account['name']}** を返却しました。",
                color=0xff9900  # オレンジ色
            )
            
            # ランク情報フィールド
            dm_embed.add_field(
                name="更新後のランク", 
                value=f"{new_rank}{rank_status}", 
                inline=False
            )
            
            # Valorantの詳細情報フィールド（存在する場合）
            if self.rank_info:
                dm_embed.add_field(
                    name="Valorant詳細情報",
                    value=(
                        f"**ティア内ランキング:** {self.rank_info['tier_ranking']}\n"
                        f"**最後のゲームでのMMR変化:** {self.rank_info['mmr_change']}\n"
                        f"**ELO:** {self.rank_info['elo']}\n"
                        f"**過去最高ランク:** {self.rank_info['highest_rank']} "
                        f"(シーズン: {self.rank_info['highest_rank_season']})"
                    ),
                    inline=False
                )
            
            # 返却日時をフッターに表示
            dm_embed.set_footer(
                text=f"返却日時: {datetime.datetime.now(TOKYO_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
            
            # 埋め込みメッセージをDMで送信
            await interaction.user.send(embed=dm_embed)
            await interaction.response.send_message(
                "アカウント返却情報をDMに送信しました。", 
                ephemeral=True
            )
        except discord.errors.Forbidden:
            # DMが送信できない場合は従来通り（埋め込み形式で）
            embed = discord.Embed(
                title=f"アカウント返却完了: {self.account['name']}",
                description="**注意:** DMが無効になっているため、このメッセージが公開されることはありません。",
                color=0xff9900
            )
            
            # ランク情報とその他の詳細を追加
            embed.add_field(
                name="返却情報", 
                value=(
                    f"アカウント **{self.account['name']}** を返却しました。\n"
                    f"**新しいランク:** {new_rank}{rank_status}"
                ), 
                inline=False
            )
            
            if self.rank_info:
                embed.add_field(
                    name="Valorant詳細情報",
                    value=(
                        f"**ティア内ランキング:** {self.rank_info['tier_ranking']}\n"
                        f"**最後のゲームでのMMR変化:** {self.rank_info['mmr_change']}\n"
                        f"**ELO:** {self.rank_info['elo']}\n"
                        f"**過去最高ランク:** {self.rank_info['highest_rank']} "
                        f"(シーズン: {self.rank_info['highest_rank_season']})"
                    ),
                    inline=False
                )
            
            embed.set_footer(
                text=f"返却日時: {datetime.datetime.now(TOKYO_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # チャンネルが存在すれば返却通知を埋め込み形式で送信
        if channel:
            embed = discord.Embed(
                title="アカウント返却通知",
                description=(
                    f"{user.mention if user else '不明なユーザー'} が "
                    f"**{self.account['name']}** を返却しました！"
                ),
                color=0xff9900  # オレンジ色
            )
            embed.add_field(
                name="更新後のランク", 
                value=f"{new_rank}{rank_status}", 
                inline=False
            )
            
            if self.rank_info:
                embed.add_field(
                    name="Valorant詳細情報",
                    value=(
                        f"**ティア内ランキング:** {self.rank_info['tier_ranking']}\n"
                        f"**最後のゲームでのMMR変化:** {self.rank_info['mmr_change']}\n"
                        f"**ELO:** {self.rank_info['elo']}\n"
                        f"**過去最高ランク:** {self.rank_info['highest_rank']} "
                        f"(シーズン: {self.rank_info['highest_rank_season']})"
                    ),
                    inline=False
                )
            
            await channel.send(embed=embed)
        else:
            logging.warning("アカウント返却: チャンネルが見つからないため、返却通知を送信できません") 