# Development — 作業再開の入口

新しいチャットではこのファイル、現在のGit状態、関連PR、[FLAME_NOTES.md](FLAME_NOTES.md)
を確認する。恒久ルールは [PROJECT_INSTRUCTIONS.md](PROJECT_INSTRUCTIONS.md)。
配置・検証手順は [DEV_WORKFLOW.md](DEV_WORKFLOW.md)。

## 2026-10-09確認時点の公開repo

main: `1764a9f258f4f9e788652a9ba37a9864dfcfdb15`。
これは監査時点のsnapshotで、現在値はGitHub/Gitで再取得する。

| Branch | 当時のhead | 状態 |
| --- | --- | --- |
| main | 1764a9f | Rename PR #1、Delete Markers PR #2がmerge済み |
| feature/rename-v1 | 11cac2e | [PR #1](https://github.com/71233/dg-python-scripts/pull/1) merged |
| feature/delete-markers-v1 | dc6b66b | [PR #2](https://github.com/71233/dg-python-scripts/pull/2) merged |
| feature/status-hud-v1 | 945fac7 | [PR #3](https://github.com/71233/dg-python-scripts/pull/3) open、データソースProbe段階 |
| chore/naming-cleanup | 91587e0 | branchあり、PR一覧では対応PRなし |
| test/2025-caption-probe | a925c67 | branchあり、PR一覧では対応PRなし |

構成: `bootstrap/dgpy_bootstrap.py` → `src/dg_python_scripts`。
TOML config、generic extension loader、Rename、Delete Markers、SelectionBroker、共通UIがある。
Internal repoの開発状態・Probe一覧・非公開結果はInternalの `docs/DEVELOPMENT.md` に置く。

## 開発環境補助の変更

branch: `chore/dev-workflow`、[PR #4](https://github.com/71233/dg-python-scripts/pull/4) (draft)。既存Status HUDとは独立した変更。
`tools/dgpy_dev.py`は更新・状態・branch切替・symlink配置・環境表示・安定したtool installを提供。
既存配置保護とGit操作の安全条件はDEV_WORKFLOWに記載。
既存CIはLinux上でPython 3.11のsuiteとwheelを検証する。
Macはローカルテストで確認。今回、GitHub認証にworkflow scopeが無いためCI設定のMac matrix追加は含めない。

- ローカルMacのPython 3.9.6: helperのGit/symlink安全性テスト21件成功。
- ローカルMacのPython 3.12.14: Public suite 67件、Internal統合4件成功。両wheel build成功。
- CIのPython 3.11: PR checksを確認すること。
- Flame 2025.2.7 Mac/Linux実機検証: **未実施**。DEV_WORKFLOWの手順を実施して結果を追加する。
- ChatGPT Project設定: PROJECT_INSTRUCTIONSの本文を設定へ反映する必要がある。
  リポジトリ文書・AGENTS.mdの追加だけではChatGPTのProject設定は更新されない。

## 作業を終えるとき

このファイルに作業branch、PRリンク、最終検証、未解決点、次の具体的操作を更新する。
機能ごとの仕様・実測結果はFLAME_NOTES、非公開の詳細はInternalへ保存する。
GitHubで新しい変更が入ったら上記snapshotを現在値として扱わない。

Public PR #4のLinux/Python 3.11 CI成功を確認。Internal CIには既存の空Media Panel判定の
不整合があり、修正パッチと権限上の制約はInternalのDEVELOPMENTに記録した。
