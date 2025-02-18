# ベースイメージとして公式のPythonイメージを使用
FROM python:3.11-slim

# 環境変数の設定
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 作業ディレクトリの作成
WORKDIR /app

# 必要なシステムパッケージのインストール（必要に応じて追加）
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Pythonの依存関係をインストール
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# アプリケーションのソースコードをコピー
COPY . .

# ボットの実行
# 環境変数からDISCORD_TOKENを取得するように設定
CMD ["python", "main.py"]
