# Map to List Lead Collector (MVP)

Google Places APIを使って、幅広い業種・業態の企業情報を収集し、
一覧表示・フィルタ・メール連絡を行うMVPです。

## できること

- Google Places APIから企業情報を取得
- 取得情報をSQLiteに保存
- 会社名/住所/URLで検索、業種/業界でフィルタ
- 選択企業に対してメール送信（初期設定はdry-run）
- 問い合わせフォーム送信アダプタ（対応サイトを限定して段階導入）
- 配信停止管理 / 日次送信上限 / 監査ログ
- Google Placesのtypeを使った業種/業界分類 + 手動タグ編集

## 画面構成・データ定義

- 画面構成（検索画面、一覧、マイリスト、履歴）とデータ項目定義（企業情報、マイリスト、送信ログ）は `docs/screen-and-data-definition.md` を参照してください。

## 取得項目

- 会社名
- WebサイトURL
- 電話番号
- メールアドレス（公式サイトから抽出できた場合のみ）
- 住所
- 業種 / 業界（Google Places typeベース分類）

## セットアップ

1. 依存ライブラリをインストール

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 環境変数を設定

```bash
export GOOGLE_MAPS_API_KEY="your_google_maps_api_key"

# メール送信を有効化する場合
export EMAIL_DRY_RUN="false"
export FORM_DRY_RUN="true"
export DAILY_SEND_LIMIT="100"
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
export SMTP_USER="user@example.com"
export SMTP_PASS="password"
export FROM_EMAIL="sales@example.com"
export CONTACT_FROM_NAME="Map to List"
```

※ デフォルトでは `EMAIL_DRY_RUN=true` で実際には送信されず、ログ保存のみ行います。

3. サーバー起動

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. ブラウザで開く

```text
http://localhost:8000
```

Codespaces / Dev Container では、`PORTS` タブで `8000` を `Open in Browser` してください。

## UIからAPIキーを設定する手順

1. Google Cloudをお持ちでない場合
	- Googleアカウントを作成（既にあれば不要）
	- Google Cloud Console にサインイン
	- 初回利用ウィザードで利用規約に同意
	- 請求先アカウント（課金）を作成
2. Google Cloud Consoleで対象プロジェクトを選択（なければ「新しいプロジェクト」を作成）
3. 「APIとサービス」→「ライブラリ」で `Places API` を有効化
4. 「APIとサービス」→「認証情報」→「認証情報を作成」→「APIキー」を作成
5. 作成したキーで「APIの制限」を開き、`Places API` のみ許可
6. 必要に応じて「アプリケーションの制限」を設定
	- 初回は制限を弱めて疎通確認し、動作確認後に厳しくするのが安全
7. 本アプリの左メニュー `APIキー設定` を開く
8. `GOOGLE_MAPS_API_KEY` 入力欄にキーを貼り付けて保存
9. 画面に `設定済み: xxxxxx...xxxx` が表示されることを確認
10. 左メニュー `データ取得` で次を入力してテスト取り込み
	- キーワード例: `カフェ 東京` / `自動車整備 横浜` / `税理士 大阪`
	- 業種プリセットは入力欄で絞り込み可能（例: カフェ, 病院, 不動産）
	- 最大件数: `5` など小さめ
11. 取り込み後、`企業一覧・検索` でデータが追加されていることを確認

### うまくいかない場合の確認

1. APIキー未設定エラー
	- `APIキー設定` で再保存し、`設定済み` 表示を確認
2. REQUEST_DENIED / APIエラー
	- Google Cloudで `Places API` 有効化済みか
	- APIキーのAPI制限が `Places API` を許可しているか
3. 権限/ネットワークエラー
	- アプリケーション制限（HTTPリファラ / IP）が実行環境と一致しているか
4. 課金関連エラー
	- Google Cloudプロジェクトで課金が有効か

## API概要

- `POST /api/import/google-places`
	- 企業情報をGoogle Placesから取り込み
	- `place_type` を指定すると、選択業種のtypeを持つ企業に絞って取り込み
- `GET /api/leads`
	- 一覧取得（検索・フィルタ）
- `POST /api/contact/email`
	- 選択した企業にメール送信（またはdry-runログ）
- `POST /api/contact/form`
	- 対応アダプタがあるサイトにフォーム送信（またはdry-runログ）
- `POST /api/form-adapters`
	- ドメイン単位でフォーム送信アダプタを登録/更新
- `POST /api/suppressions`
	- 配信停止アドレスを登録
- `POST /api/leads/tags/bulk`
	- 選択企業に手動タグ（業種/業界）を一括反映
- `GET /api/audit-logs`
	- 監査ログを取得

## フォーム送信アダプタの段階導入

1. まず少数ドメインだけ `POST /api/form-adapters` で登録
2. `FORM_DRY_RUN=true` でログのみ検証
3. 問題がなければ `FORM_DRY_RUN=false` に変更
4. 対応ドメインを段階的に追加

## 重要な注意

- Google Mapsの情報取得は必ず公式APIと利用規約に従ってください。
- 問い合わせメール送信時は、関連法令・利用規約を遵守してください。
- 問い合わせフォーム自動送信は、サイト側制限(CAPTCHA等)により非対応の場合があります。

## GitHub Pagesで公開する

このアプリはFastAPIバックエンドが必要なため、GitHub Pagesだけでは完結しません。
公開構成は次の2段にします。

- フロント: GitHub Pages
- バックエンドAPI: Render / Railway / Fly.io など

### 1. バックエンドを先に公開

公開先の環境変数に最低限以下を設定してください。

```bash
SESSION_SECRET=十分長いランダム文字列
DISABLE_GOOGLE_LOGIN=false
CORS_ALLOW_ORIGINS=https://macdown360.github.io
```

GitHub Pages のURLが `https://<owner>.github.io/<repo>/` の場合でも、
`CORS_ALLOW_ORIGINS` にはオリジン部分の `https://<owner>.github.io` を設定してください。
例: `https://macdown360.github.io/maptolist/` で公開する場合は `https://macdown360.github.io`

### 2. GitHub Pagesデプロイ

このリポジトリには `/.github/workflows/pages.yml` を追加済みです。
`main` へのpushでPagesが自動デプロイされます。

1. GitHubの `Settings > Pages` で `GitHub Actions` を選択
2. `Settings > Secrets and variables > Actions > Variables` に次を追加
	- `PAGES_API_BASE_URL=https://<your-backend-domain>`
3. `main` にpush（または Actions の `Deploy GitHub Pages` を手動実行）

ビルド時に `scripts/build_pages.sh` が静的ファイルを生成し、
Pages側のフロントから `PAGES_API_BASE_URL` へAPIリクエストします。