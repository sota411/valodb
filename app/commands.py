import logging
import asyncio
import discord
from discord import app_commands
from .valorant_api import get_valorant_rank
from .accounts import (
    TOKYO_TZ, borrowed_accounts, user_status, 
    auto_return_account, is_account_borrowed, get_return_time_str
)
from .modals import AccountRegisterModal, RankUpdateModal
from .kabaneri import kabaneri_command


# コマンド登録関数
def register_commands(bot, sheet, sheet_append_row, sheet_update_cell, 
                      get_all_accounts):
    """
    スラッシュコマンドを登録
    
    Args:
        bot: Discordボット
        sheet: スプレッドシート
        sheet_append_row: 行追加関数
        sheet_update_cell: セル更新関数
        get_all_accounts: アカウント一覧取得関数
    """
    tree = bot.tree
    
    # /register コマンド
    @tree.command(name="register", description="新規アカウントを登録します")
    async def register(interaction: discord.Interaction):
        modal = AccountRegisterModal(sheet_append_row)
        await interaction.response.send_modal(modal)

    # /use_account コマンド（アカウント借用）
    @tree.command(name="use_account", description="アカウントを借りる")
    async def use_account(interaction: discord.Interaction):
        if is_account_borrowed(interaction.user.id):
            await interaction.response.send_message(
                "すでにアカウントを借りています。返却してください。",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            accounts = await get_all_accounts(sheet)
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
                    await sheet_update_cell(selected_account["row"], 5, "borrowed")
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

                # 自動返却タスクを作成
                task = asyncio.create_task(
                    auto_return_account(
                        interaction.user.id, 
                        selected_account, 
                        guild_id, 
                        channel_id,
                        bot,
                        sheet_update_cell
                    )
                )
                borrowed_accounts[interaction.user.id]["task"] = task

                return_time_str = get_return_time_str()
                
                # Valorantのより詳細なランク情報を取得
                rank_info = None
                rank_update_success = False
                
                if "val_username" in selected_account and "val_tag" in selected_account:
                    val_username = selected_account.get("val_username")
                    val_tag = selected_account.get("val_tag")
                    
                    if val_username and val_tag:
                        logging.info(
                            f"アカウント借用: Valorantランク情報取得試行 - {val_username}#{val_tag}"
                        )
                        
                        try:
                            rank_info = get_valorant_rank("ap", val_username, val_tag)
                            
                            # 取得に成功した場合はスプレッドシートのランク情報を更新
                            if rank_info:
                                logging.info(
                                    f"アカウント借用: ランク情報取得成功 - {val_username}#{val_tag}, "
                                    f"Rank: {rank_info['current_rank']}"
                                )
                                
                                try:
                                    # スプレッドシートのランク列（4列目）を更新
                                    await sheet_update_cell(
                                        selected_account["row"], 
                                        4, 
                                        rank_info["current_rank"]
                                    )
                                    logging.info(
                                        f"アカウント借用: スプレッドシートのランク更新成功 - "
                                        f"row: {selected_account['row']}, "
                                        f"rank: {rank_info['current_rank']}"
                                    )
                                    
                                    # メモリ上のアカウント情報も更新
                                    selected_account["rank"] = rank_info["current_rank"]
                                    rank_update_success = True
                                except Exception as e:
                                    logging.error(
                                        f"アカウント借用: スプレッドシートのランク更新エラー - {str(e)}", 
                                        exc_info=True
                                    )
                                    import traceback
                                    logging.error(traceback.format_exc())
                            else:
                                logging.warning(
                                    f"アカウント借用: ランク情報取得失敗 - {val_username}#{val_tag}"
                                )
                        except Exception as e:
                            logging.error(f"Valorantランク情報更新エラー: {str(e)}", exc_info=True)
                            import traceback
                            logging.error(traceback.format_exc())
                    else:
                        logging.warning(
                            f"アカウント借用: ユーザー名またはタグが空 - "
                            f"username: '{val_username}', tag: '{val_tag}'"
                        )
                else:
                    logging.warning(
                        "アカウント借用: Valorant情報なし - "
                        "val_usernameまたはval_tagがアカウント情報に存在しません"
                    )
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
                    account_details += (
                        f"\n**Valorant:** {selected_account['val_username']}#"
                        f"{selected_account['val_tag']}"
                    )
                
                # Valorantの詳細情報がある場合は追加
                if rank_info:
                    account_details += (
                        f"\n\n**Valorant詳細情報:**\n"
                        f"**現在のランク:** {rank_info['current_rank']}\n"
                        f"**ティア内ランキング:** {rank_info['tier_ranking']}\n"
                        f"**最後のゲームでのMMR変化:** {rank_info['mmr_change']}\n"
                        f"**ELO:** {rank_info['elo']}\n"
                        f"**過去最高ランク:** {rank_info['highest_rank']} "
                        f"(シーズン: {rank_info['highest_rank_season']})\n"
                    )
                elif "val_username" in selected_account and "val_tag" in selected_account:
                    account_details += "\n\n**注意:** Valorantの詳細情報を取得できませんでした。"
                
                account_details += f"\n**返却期限:** {return_time_str}\n"
                
                # DMに詳細情報を埋め込み形式で送信
                try:
                    # 埋め込みメッセージを作成
                    dm_embed = discord.Embed(
                        title=f"アカウント情報: {selected_account['name']}",
                        description="アカウントの貸出が完了しました。以下の情報を使用してログインしてください。",
                        color=0x00ff00  # 緑色
                    )
                    
                    # 基本情報フィールド
                    dm_embed.add_field(
                        name="基本情報",
                        value=(
                            f"**Name:** {selected_account['name']}\n"
                            f"**ID:** {selected_account['id']}\n"
                            f"**Password:** {selected_account['password']}\n"
                            f"**Rank:** {selected_account['rank']}"
                            f"{' (自動更新済み)' if rank_update_success else ''}"
                        ),
                        inline=False
                    )
                    
                    # Valorantユーザー情報フィールド
                    if "val_username" in selected_account and "val_tag" in selected_account:
                        dm_embed.add_field(
                            name="Valorant アカウント",
                            value=(
                                f"{selected_account['val_username']}#"
                                f"{selected_account['val_tag']}"
                            ),
                            inline=False
                        )
                    
                    # Valorantの詳細情報フィールド
                    if rank_info:
                        dm_embed.add_field(
                            name="Valorant詳細情報",
                            value=(
                                f"**現在のランク:** {rank_info['current_rank']}\n"
                                f"**ティア内ランキング:** {rank_info['tier_ranking']}\n"
                                f"**最後のゲームでのMMR変化:** {rank_info['mmr_change']}\n"
                                f"**ELO:** {rank_info['elo']}\n"
                                f"**過去最高ランク:** {rank_info['highest_rank']} "
                                f"(シーズン: {rank_info['highest_rank_season']})"
                            ),
                            inline=False
                        )
                    elif "val_username" in selected_account and "val_tag" in selected_account:
                        dm_embed.add_field(
                            name="注意",
                            value="Valorantの詳細情報を取得できませんでした。",
                            inline=False
                        )
                    
                    # 返却期限
                    dm_embed.set_footer(text=f"返却期限: {return_time_str}")
                    
                    # 埋め込みメッセージをDMで送信
                    await interaction.user.send(embed=dm_embed)
                    await interaction.followup.send("アカウント情報をDMに送信しました。", ephemeral=True)
                except discord.errors.Forbidden:
                    # DMが送信できない場合は従来通り（埋め込み形式で）
                    embed = discord.Embed(
                        title=f"アカウント情報: {selected_account['name']}",
                        description="**注意:** DMが無効になっているため、このメッセージが公開されることはありません。",
                        color=0x00ff00
                    )
                    
                    # アカウント情報（DMと同じ内容）
                    embed.add_field(
                        name="基本情報",
                        value=(
                            f"**Name:** {selected_account['name']}\n"
                            f"**ID:** {selected_account['id']}\n"
                            f"**Password:** {selected_account['password']}\n"
                            f"**Rank:** {selected_account['rank']}"
                            f"{' (自動更新済み)' if rank_update_success else ''}"
                        ),
                        inline=False
                    )
                    
                    if "val_username" in selected_account and "val_tag" in selected_account:
                        embed.add_field(
                            name="Valorant アカウント",
                            value=(
                                f"{selected_account['val_username']}#"
                                f"{selected_account['val_tag']}"
                            ),
                            inline=False
                        )
                    
                    if rank_info:
                        embed.add_field(
                            name="Valorant詳細情報",
                            value=(
                                f"**現在のランク:** {rank_info['current_rank']}\n"
                                f"**ティア内ランキング:** {rank_info['tier_ranking']}\n"
                                f"**最後のゲームでのMMR変化:** {rank_info['mmr_change']}\n"
                                f"**ELO:** {rank_info['elo']}\n"
                                f"**過去最高ランク:** {rank_info['highest_rank']} "
                                f"(シーズン: {rank_info['highest_rank_season']})"
                            ),
                            inline=False
                        )
                    elif "val_username" in selected_account and "val_tag" in selected_account:
                        embed.add_field(
                            name="注意",
                            value="Valorantの詳細情報を取得できませんでした。",
                            inline=False
                        )
                    
                    embed.set_footer(text=f"返却期限: {return_time_str}")
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)

                # チャンネルにメンション付きメッセージを埋め込み形式で送信
                embed = discord.Embed(
                    title="アカウント借用通知",
                    description=(
                        f"{interaction.user.mention} が "
                        f"**{selected_account['name']}** を借りました！"
                    ),
                    color=0x00ff00  # 緑色
                )
                embed.set_footer(text=f"返却期限: {return_time_str}")
                await interaction.channel.send(embed=embed)

        view = discord.ui.View()
        view.add_item(AccountDropdown())
        await interaction.followup.send("アカウントを選択してください:", view=view, ephemeral=True)

    # /update_ranks コマンド
    @tree.command(
        name="update_ranks", 
        description="すべてのアカウントのランク情報を一括更新します"
    )
    async def update_ranks(interaction: discord.Interaction, status: str = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "このコマンドは管理者のみ使用できます。",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        
        try:
            accounts = await get_all_accounts(sheet)
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
                    await progress_message.edit(
                        content=f"{progress_percent}% 完了 ({i}/{len(target_accounts)})"
                    )
                except:
                    pass
            
            if (
                "val_username" not in account or 
                "val_tag" not in account or 
                not account.get("val_username") or 
                not account.get("val_tag")
            ):
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
                        await sheet_update_cell(
                            account["row"], 4, new_rank
                        )
                        logging.info(
                            f"ランク更新: {val_username}#{val_tag} - {old_rank} -> {new_rank}"
                        )
                        account["rank"] = new_rank
                        updated_accounts.append({
                            "name": account["name"],
                            "old_rank": old_rank,
                            "new_rank": new_rank
                        })
                    
                    success_count += 1
                else:
                    fail_count += 1
                    logging.warning(
                        f"一括ランク更新: {val_username}#{val_tag} のランク情報取得に失敗しました"
                    )
            except Exception as e:
                fail_count += 1
                logging.error(
                    f"一括ランク更新エラー ({val_username}#{val_tag}): {str(e)}", 
                    exc_info=True
                )
            
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
            embed = discord.Embed(
                title="ランク情報更新通知",
                description=(
                    f"**{interaction.user.display_name} がアカウントのランク情報を更新しました**\n"
                    f"更新されたアカウント: {len(updated_accounts)}件"
                ),
                color=0x0099ff  # 青色
            )
            
            account_list = ""
            for acc in updated_accounts[:10]:  # 長すぎる場合は最初の10件のみ表示
                account_list += f"- {acc['name']}: {acc['old_rank']} → {acc['new_rank']}\n"
            
            if len(updated_accounts) > 10:
                account_list += f"...ほか {len(updated_accounts) - 10}件\n"
            
            embed.add_field(name="更新されたアカウント", value=account_list, inline=False)
            await interaction.channel.send(embed=embed)

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
        try:
            cell_status = sheet.cell(account["row"], 5).value
            if not account or cell_status != "borrowed":
                borrowed_accounts.pop(interaction.user.id, None)
                user_status.pop(interaction.user.id, None)
                if task:
                    task.cancel()
                await interaction.response.send_message(
                    "アカウントの借用状態が不整合でしたが、自動的にリセットしました。再度借用してください。",
                    ephemeral=True
                )
                return
        except Exception as e:
            logging.error(f"スプレッドシートからの状態確認エラー: {e}")
            # エラーが発生しても処理は継続

        if task:
            task.cancel()

        modal = RankUpdateModal(
            account, 
            sheet_update_cell, 
            borrowed_accounts, 
            user_status, 
            guild_id, 
            channel_id, 
            bot
        )
        await interaction.response.send_modal(modal)

    # /remove_comment コマンド（コメント削除）
    @tree.command(
        name="remove_comment", 
        description="コードブロック、画像、ファイルを除くコメントを削除します。"
    )
    async def remove_comment(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "このコマンドを使用する権限がありません。", 
                ephemeral=True
            )
            return

        await interaction.response.defer()

        channel = interaction.channel
        import datetime
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
            f"削除が完了しました！\n- 一括削除: {bulk_deleted_count} 件\n"
            f"- 個別削除: {async_deleted_count} 件\n- 合計: {total_deleted} 件"
        )

    # /reset_borrowed コマンド（管理者専用：借用状態の手動リセット）
    @tree.command(
        name="reset_borrowed", 
        description="借用状態を手動でリセットします（管理者専用）"
    )
    async def reset_borrowed(interaction: discord.Interaction, user_id: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "このコマンドを使用する権限がありません。", 
                ephemeral=True
            )
            return

        try:
            user_id_int = int(user_id)
            if user_id_int in borrowed_accounts:
                account_info = borrowed_accounts.pop(user_id_int)
                user_status.pop(user_id_int, None)
                task = account_info.get("task")
                if task:
                    task.cancel()
                await interaction.response.send_message(
                    f"ユーザーID {user_id} の借用状態をリセットしました。", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"ユーザーID {user_id} は借用状態ではありません。", 
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "正しいユーザーIDを入力してください。", 
                ephemeral=True
            )

    # /kabaneri コマンド
    @tree.command(name="kabaneri", description="六根清浄！")
    async def kabaneri(interaction: discord.Interaction):
        await kabaneri_command(interaction)

    # コマンド登録完了
    return tree 