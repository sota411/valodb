import os
import json
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials



# Googleスプレッドシートの認証設定と初期化
def init_spreadsheet():
    """
    Googleスプレッドシートの初期設定を行う
    
    Returns:
        gspread.models.Worksheet: スプレッドシートのワークシート
    """
    try:
        scope = ["https://spreadsheets.google.com/feeds", 
                "https://www.googleapis.com/auth/drive"]
        credentials_info = json.loads(os.getenv("CREDENTIALS_JSON"))
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            credentials_info, scope
        )
        gc = gspread.authorize(credentials)
        sheet = gc.open("Accounts").sheet1  # スプレッドシート名を指定
        logging.info("スプレッドシートの初期化に成功しました")
        return sheet
    except Exception as e:
        logging.error(f"スプレッドシートの初期化に失敗しました: {str(e)}", exc_info=True)
        import traceback
        logging.error(traceback.format_exc())
        raise



# アカウント一覧を取得
async def get_all_accounts(sheet):
    """
    スプレッドシートからすべてのアカウント情報を取得
    
    Args:
        sheet: スプレッドシートのワークシート
        
    Returns:
        list: アカウント情報のリスト
    """
    import asyncio
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, sheet.get_all_records
        )
    except Exception as e:
        logging.error(f"アカウント情報取得エラー: {str(e)}", exc_info=True)
        import traceback
        logging.error(traceback.format_exc())
        return []



# スプレッドシートの特定のセルを更新
async def update_cell(sheet, row, col, value):
    """
    スプレッドシートの特定のセルを更新
    
    Args:
        sheet: スプレッドシートのワークシート
        row (int): 行番号
        col (int): 列番号
        value: 設定する値
    """
    import asyncio
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, sheet.update_cell, row, col, value
        )
        logging.info(f"セル更新: ({row}, {col}) = {value}")
        return True
    except Exception as e:
        logging.error(
            f"セル更新エラー: ({row}, {col}) = {value}: {str(e)}", 
            exc_info=True
        )
        import traceback
        logging.error(traceback.format_exc())
        return False



# スプレッドシートに行を追加
async def append_row(sheet, row_data):
    """
    スプレッドシートに行を追加
    
    Args:
        sheet: スプレッドシートのワークシート
        row_data (list): 追加する行のデータリスト
    """
    import asyncio
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, sheet.append_row, row_data
        )
        logging.info(f"行追加: {row_data}")
        return True
    except Exception as e:
        logging.error(f"行追加エラー: {row_data}: {str(e)}", exc_info=True)
        import traceback
        logging.error(traceback.format_exc())
        return False 