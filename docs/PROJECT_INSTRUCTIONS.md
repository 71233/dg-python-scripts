# DGpy — Project Instructions

この本文をChatGPT Project Instructionsに設定する。ここには恒久ルールだけを置く。
現在のバージョン、完成状態、branch、PR、実測結果、未解決事項はGitHubの文書で管理する。

- このProjectはAutodesk Flame向けPython Toolkit「DGpy」の設計・実装・検証を行う。
- 公開可能なCoreは `71233/dg-python-scripts`、社内コード・Probe・非公開の検証情報は `71233/dg-python-scripts-internal` に置く。依存方向はInternal → Publicのみ。社内パス、ホスト名、認証情報、私有ログをPublicへ入れない。
- 作業開始時に両repoの現在のbranch、commit、working tree、関連PR、実際のコードを確認する。`docs/DEVELOPMENT.md` と `docs/FLAME_NOTES.md` を読み、チャット履歴より現在のコードと証拠を優先する。古い文書とコードが食い違う場合は食い違いを記録して確認する。
- 既存branchやPRが同じ目的を扱っていれば再利用する。ユーザーの未保存の変更や既存配置を保護し、無断でreset、強制checkout、上書き、削除、mergeしない。
- Flame API依存、selection、UI、業務ロジックを可能な範囲で分離する。Flame/Qtのimportは必要時に行い、バージョン差の影響を局所化する。不要なmonkey patch、常駐処理、global stateを増やさない。
- API挙動が不明なら既存コード、Autodeskの対象バージョンの資料、最小Probe、実機確認の順で調べる。仕様・推測・実測を区別し、未確認の挙動を確認済みと書かない。破壊的Probeは使い捨ての検証対象に限定する。
- SelectionとUIは現在の共通実装・検証記録に従う。メニュー名の不要なDGpy重複を避け、Mac/Linuxで自然に動くQt layoutを優先する。
- 開発配置はcheckoutへのsymlinkを基本とする。repo全体やsrcをFlame hook検索先へ配置しない。既存hookを保護し、二重読み込みを確認する。検証記録にはrepo、branch、commit、tree状態、OS、Flameバージョンを含める。
- 作業を区切る際はGitHubの開発状態、PR、検証記録、未解決事項、次の操作を更新する。Project Instructionsへ進捗を追加しない。別チャットへの引き継ぎは該当GitHub文書・PRへのリンクと作業目的で済む状態を維持する。
