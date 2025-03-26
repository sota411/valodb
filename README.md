# Valorant Discord Bot

Valorantのアカウント管理とランク情報の取得・表示を行うDiscord Botです。

## 機能

- アカウント登録: `/register` コマンドでValorantアカウントを登録
- アカウント借用: `/use_account` コマンドでアカウントを借りる
- アカウント返却: `/return_account` コマンドでアカウントを返却
- ランク更新: `/update_ranks` コマンドで全アカウントのランク情報を更新
- コメント削除: `/remove_comment` コマンドでチャンネルのコメントを削除
- 借用状態リセット: `/reset_borrowed` コマンドで借用状態を手動リセット
- カバネリゲーム: `/kabaneri` コマンドでミニゲームを実行

## ファイル構成

- `main.py`: メインプログラム、Botの起動とコマンド登録
- `valorant_api.py`: Valorant APIとの連携機能
- `spreadsheet.py`: Googleスプレッドシートとの連携機能
- `accounts.py`: アカウント管理に関する機能
- `modals.py`: 各種モーダルUI
- `commands.py`: スラッシュコマンドの実装
- `kabaneri.py`: カバネリミニゲーム機能
- `keep_alive.py`: Flaskサーバーでのヘルスチェック機能

## 環境変数

- `TOKEN`: Discord Botのトークン
- `VALO_API_KEY`: Valorant APIキー
- `CREDENTIALS_JSON`: GoogleスプレッドシートのAPIクレデンシャル（JSON形式）

## インストール

```bash
pip install -e .
```

## 使い方

### 直接実行

```bash
python -m app.main
```

### インストール後

```bash
valodb
```

## デプロイ

Koyebでのデプロイに対応しています。Koyebの環境変数設定で必要な環境変数を設定し、ビルドコマンドを適宜設定してください。

## 注意事項

- アカウントは5時間後に自動的に返却されます
- ランク情報はAPIから自動取得されます 