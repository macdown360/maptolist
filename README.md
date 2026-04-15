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
export GOOGLE_PLACES_API_KEY="your_google_places_api_key"

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
8. `GOOGLE_PLACES_API_KEY` 入力欄にキーを貼り付けて保存
9. 画面に `設定済み: xxxxxx...xxxx` が表示されることを確認
10. 左メニュー `データ取得` で次を入力してテスト取り込み
	- キーワード例: `カフェ 東京` / `自動車整備 横浜` / `税理士 大阪`
	- 業種プリセットは入力欄で絞り込み可能（例: カフェ, 病院, 不動産）
	- 最大件数: `5` など小さめ
11. 取り込み後、`企業一覧・検索` でデータが追加されていることを確認

### うまくいかない場合の確認

#### 【ステップ1】ブラウザで詳しいエラーを確認

1. ブラウザで `F12` キーを押して **DevTools** を開く
2. **Network** タブをクリック
3. `データ取得` で取り込みを実行
4. `/api/import/google-places` をクリック
5. **Response** タブを見て、エラーメッセージを確認

#### 【よくあるエラーと対処法】

##### ❌ REQUEST_DENIED
**原因:**
- Google Cloudプロジェクトで **Places API が有効化されていない**
- Google Cloudで **支払い方法が設定されていない**

**対処:**
1. [Google Cloud Console](https://console.cloud.google.com) へログイン
2. 左メニュー「APIとサービス」→「ライブラリ」
3. **"Places API"** を検索して、ステータスが「有効」になっているか確認
4. ≪必須≫ 「お支払い」→ 請求先アカウントが設定されているか確認
   - 無料枠では Places API は動作しません（最初は $200 の無料クレジットがあります）

##### ❌ PERMISSION_DENIED
**原因:**
- APIキーに **HTTPリファラ制限** または **IP制限** が設定されている可能性

**対処:**
1. [Google Cloud Console](https://console.cloud.google.com) へログイン
2. 左メニュー「APIとサービス」→「認証情報」
3. 作成したAPIキーをクリック
4. 「APIの制限」セクションで `Places API` が選択されているか確認
5. 「アプリケーションの制限」セクションを確認：
   - ❌ **HTTPリファラー（ウェブサイト）が設定されている場合**
     - リファラ設定を **「制限なし」に変更する**（テスト段階）
     - または本番ドメイン（例: `https://maptolist.online`）を許可リストに追加
   - ❌ **IP アドレス制限が設定されている場合**
     - 「制限なし」に変更する
6. 変更後、ブラウザをハードリロード（Ctrl+Shift+R）して再試行

##### ❌ クロスオリジン要求がブロックされた
**原因:**
- バックエンド側の CORS 設定が本番ドメインを許可していない

**対処:**
- 本アプリの管理者に以下を確認してもらう
  - 環境変数 `CORS_ALLOW_ORIGINS` に本番ドメインが含まれているか
  - 例: `https://maptolist.online` が許可リストに入っているか

#### 【APIキー作成時の推奨設定】

本番環境への展開時の安全な設定：

1. **初期テスト段階（推奨）**
   - 「アプリケーションの制限」→ **「制限なし」**
   - 取得できることを確認

2. **本番環境での制限設定（セキュリティ向上後）**
   - 「アプリケーションの制限」→ **「HTTPリファラー（ウェブサイト）」**
   - 許可リスト: `https://maptolist.online/*`
   - または IP 制限を追加

#### 【よくある間違い】

- ❌ 「API制限」で `Maps API` を選択している（`Places API` ではなく）
- ❌ APIキーを作成したが、`Places API` を有効化してない
- ❌ Google Cloudプロジェクトに支払い方法が登録されていない
- ❌ HTTPリファラ制限で、許可されていないドメインからアクセスしている

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
DISABLE_GOOGLE_LOGIN=true
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

### APIキー設定が保存できない場合

GitHub Pages公開時に `APIキー設定` が保存できない主な原因は次の2つです。

- `PAGES_API_BASE_URL` が未設定で、Pages側からバックエンドURLが分からない
- Pages (`github.io`) から別ドメインのFastAPIへアクセスする際に認証Cookieが必要

このリポジトリでは、Pages公開時に認証Cookieを含めてAPIへアクセスするよう対応済みです。
そのため、まず GitHub Actions Variables に `PAGES_API_BASE_URL` を正しく設定してください。

### ログインしない運用（ブラウザ保存方式）

ログインを使わない場合、Google Places APIキーはサーバーではなくブラウザに保存して利用できます。

- `APIキー設定` で入力したキーを `localStorage` に保存
- `データ取得` 実行時に、そのキーをリクエストへ付与して取り込み

注意:

- ブラウザごと・端末ごとに別管理です（他端末には引き継がれません）
- ブラウザのストレージ削除でキーも消えます
- ログインしない運用では `DISABLE_GOOGLE_LOGIN=true` が必須です

## バックエンドを最短で公開する（Render）

このリポジトリには Render 用の設定ファイル [render.yaml](render.yaml) を追加済みです。

1. Render に GitHub 連携でログイン
2. `New +` → `Blueprint` を選択
3. `macdown360/maptolist` を選んでデプロイ
4. Render 側で次の環境変数を設定
	- `DISABLE_GOOGLE_LOGIN=true`
	- `CORS_ALLOW_ORIGINS=https://macdown360.github.io`
	- （任意）Googleログインを後で有効化する場合のみ `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
5. デプロイ完了後、表示されるURL（例: `https://maptolist-api.onrender.com`）を控える

次に GitHub 側でフロントの接続先を設定します。

1. `Settings` → `Secrets and variables` → `Actions` → `Variables`
2. `PAGES_API_BASE_URL` を作成し、値に Render のURLを設定
3. `main` に push（または `Deploy GitHub Pages` を手動実行）

これで GitHub Pages の `APIキー設定` から保存できるようになります。