import os
import logging
import traceback
import valo_api

# Valorant API のキー設定
def setup_api():
    """Valorant APIのキー設定を行う"""
    valo_api.set_api_key(os.getenv("VALO_API_KEY"))

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
        logging.warning(
            f"Valorantユーザー名またはタグが空です: name='{name}', tag='{tag}'"
        )
        return None
        
    try:
        logging.info(
            f"Valorantランク情報取得開始: region={region}, name={name}, tag={tag}"
        )
        
        # バージョンを 'v2' として指定
        mmr_data = valo_api.get_mmr_details_by_name("v2", region, name, tag)
        
        # mmr_dataが存在するか確認
        if not mmr_data:
            logging.warning(
                f"MMRデータが取得できませんでした: region={region}, name={name}, tag={tag}"
            )
            return None
            
        # current_dataが存在するか確認
        if not hasattr(mmr_data, 'current_data') or not mmr_data.current_data:
            logging.warning(
                f"current_dataがありません: region={region}, name={name}, tag={tag}"
            )
            return None
            
        # highest_rankが存在するか確認
        if not hasattr(mmr_data, 'highest_rank') or not mmr_data.highest_rank:
            logging.warning(
                f"highest_rankがありません: region={region}, name={name}, tag={tag}"
            )
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
        logging.error(traceback.format_exc())
        return None 