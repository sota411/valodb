# ベースイメージとしてPython 3.10を使用
FROM python:3.10-slim

# 作業ディレクトリを設定
WORKDIR /app

# 必要なシステムパッケージのインストール
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 依存関係ファイルをコピー
COPY requirements.txt .
COPY setup.py .
COPY README.md .

# アプリケーションのコード全体をコピー
COPY app/ ./app/

# 依存関係のインストール
RUN pip install -e .

# 環境変数の設定
ENV PYTHONUNBUFFERED=1

# ヘルスチェック用のポートを公開
EXPOSE 8080

# アプリケーションの実行
CMD ["python", "-m", "app.main"]
