# 画面構成とデータ項目定義（検索・一覧・マイリスト・履歴）

## 1. 目的

このドキュメントは、以下の体験を実現するための画面構成とデータ定義を整理する。

- 条件で企業を抽出する
- 抽出結果から連絡対象を選び、マイリストで管理する
- マイリストからメール送信する
- 送信日時・送信回数・アプローチ内容の履歴を管理する

## 2. 画面構成

## 2.1 画面一覧

1. 検索画面（企業抽出）
2. 一覧画面（検索結果）
3. マイリスト画面（連絡対象管理）
4. 履歴画面（アプローチ履歴）

## 2.2 画面詳細

### A. 検索画面（企業抽出）

- 目的:
  - 業種・業態・地域（都道府県/市区町村）条件で対象企業を抽出する。
- 主な入力:
  - キーワード
  - 業種（例: カフェ、病院、不動産）
  - 業界（任意）
  - 都道府県
  - 市区町村（任意）
  - 取得件数上限
- 主な操作:
  - 検索実行
  - 検索条件保存（将来拡張）
- 出力:
  - 一覧画面へ検索結果を引き渡し

### B. 一覧画面（検索結果）

- 目的:
  - 抽出企業を確認し、連絡対象を選定する。
- 主な表示項目:
  - チェックボックス
  - 会社名
  - 業種 / 業界
  - 住所
  - 都道府県
  - Webサイト
  - 電話
  - メール
  - 最終連絡日
  - 累計送信回数
- 主な操作:
  - 複数選択
  - マイリストへ追加
  - 個別詳細の参照

### C. マイリスト画面（連絡対象管理）

- 目的:
  - 連絡対象企業を管理し、送信アクションを実行する。
- 主な表示項目:
  - 会社名
  - 連絡先（メール/電話）
  - ステータス（未連絡、対応中、送信済み、除外）
  - 最終送信日時
  - 送信回数
  - 担当メモ
- 主な操作:
  - メール送信（単体/一括）
  - ステータス更新
  - マイリストから除外
  - 履歴画面へ遷移

### D. 履歴画面（アプローチ履歴）

- 目的:
  - いつ・どの企業に・何を送ったかを追跡する。
- 主な表示項目:
  - 実施日時
  - 企業名
  - 実施チャネル（メール/フォーム/電話など）
  - 件名
  - 本文要約
  - 実行結果（sent, dry_run, skipped, failed など）
  - 実行者
- 主な操作:
  - 企業名/期間/結果で絞り込み
  - 履歴詳細表示
  - CSVエクスポート（将来拡張）

## 3. 画面遷移

1. 検索画面で条件指定して検索
2. 一覧画面で対象企業を選択
3. 「マイリストへ追加」で連絡対象を固定化
4. マイリスト画面でメール送信
5. 送信後、履歴画面で結果と時系列を確認

## 4. データ項目定義

## 4.1 企業情報（Lead）

### エンティティ名

- leads

### 主な項目

- id: 企業ID（内部採番）
- user_id: ユーザーID（所有者）
- place_id: 外部サービスの一意ID
- name: 会社名
- website: 公式WebサイトURL
- phone: 電話番号
- email: 代表メールアドレス
- address: 住所（全文）
- prefecture: 都道府県（将来追加推奨）
- city: 市区町村（将来追加推奨）
- category: 業種
- industry: 業界
- rating: 評価
- user_ratings_total: 評価件数
- raw_types: 元データ業種タイプ
- created_at: 作成日時
- updated_at: 更新日時

### 補足

- 現在の実装は address から都道府県/市区町村を分離保持していないため、地域軸の集計や高速検索を重視する場合は prefecture/city の正規化列追加を推奨。

## 4.2 マイリスト（My List）

### エンティティ名（新規追加推奨）

- my_list_items

### 目的

- 一覧の「一時選択」と区別し、連絡対象を永続管理する。

### 主な項目

- id: マイリスト項目ID
- user_id: ユーザーID
- lead_id: 企業ID
- status: 連絡ステータス
  - 値例: new, contacted, nurturing, closed, excluded
- priority: 優先度（low, medium, high）
- owner_name: 担当者名
- note: 営業メモ
- added_at: 追加日時
- updated_at: 更新日時
- last_contacted_at: 最終連絡日時（集計キャッシュ）
- contact_count: 累計連絡回数（集計キャッシュ）

### 一意制約

- UNIQUE(user_id, lead_id)

## 4.3 送信ログ（Approach / Contact Log）

### エンティティ名

- contact_logs

### 目的

- 1回のアプローチ実行を時系列で保存する。

### 主な項目

- id: ログID
- lead_id: 企業ID
- channel: 連絡チャネル
  - 値例: email, form, phone
- status: 実行結果
  - 値例: sent, dry_run, skipped, failed, suppressed, daily_limit, no_adapter
- subject: 件名
- message: 本文または結果メッセージ
- created_at: 実行日時

### 追加推奨項目

- user_id: 実行ユーザー
- campaign_id: 施策識別子
- template_id: 使用テンプレート
- error_code: 失敗原因コード
- metadata_json: 配信先・HTTPコードなどの付随情報

## 4.4 監査ログ（運用ログ）

### エンティティ名

- audit_logs

### 目的

- 設定変更や実行操作など、システム操作の追跡。

### 主な項目

- id
- action
- actor
- target_type
- target_id
- details
- created_at

## 5. API観点の整理

## 5.1 既存API（現状）

- GET /api/leads
- POST /api/import/google-places
- POST /api/contact/email
- POST /api/contact/form
- GET /api/audit-logs

## 5.2 追加API（マイリスト・履歴運用向け）

- GET /api/my-list
- POST /api/my-list
  - body: lead_ids[] を受け取り一括追加
- PATCH /api/my-list/{id}
  - status, priority, note 更新
- DELETE /api/my-list/{id}
- GET /api/contact-logs
  - lead_id, status, channel, from, to で絞り込み
- GET /api/leads/{lead_id}/timeline
  - 企業単位の時系列履歴

## 6. 実装優先順位（提案）

1. my_list_items テーブル追加
2. 一覧画面に「マイリストへ追加」導線を追加
3. マイリスト画面（一覧 + 送信）を追加
4. contact_logs の検索API追加（履歴画面用）
5. 履歴画面を追加（企業別タイムライン含む）

## 7. 受け入れ基準（抜粋）

- 検索条件（業種・都道府県）で対象企業を絞り込めること
- 一覧から選択した企業をマイリストへ保存できること
- マイリストからメール送信でき、結果が contact_logs に記録されること
- 企業ごとに「最終送信日時」と「送信回数」が確認できること
- 履歴画面で、誰がいつ何を送ったか追跡できること
