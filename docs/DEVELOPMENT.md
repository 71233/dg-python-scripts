# Development — 作業再開の入口

新しいチャットではこのファイル、現在のGit状態、関連PR、[FLAME_NOTES.md](FLAME_NOTES.md)
を確認する。恒久ルールは [PROJECT_INSTRUCTIONS.md](PROJECT_INSTRUCTIONS.md)。
配置・検証手順は [DEV_WORKFLOW.md](DEV_WORKFLOW.md)。

## 2026-10-09 Python入口・専用launcherの継続作業

Public [PR #4](https://github.com/71233/dg-python-scripts/pull/4)、Internal
[PR #1](https://github.com/71233/dg-python-scripts-internal/pull/1) を再利用。両PRはdraft／未merge。
開始時は両repoの `chore/dev-workflow` がcleanでGitHub headと一致:
Public `2038cce7ec0845a0c25b0b0ff459ba604e446eda`、
Internal `72611184cc52500c60655a79f8a2cae757bec33f`。
main、他branch、既存PR metadata、両repoの実コードと仕様文書を再確認した。

ユーザーは従来のPublicメニュー、About/Diagnostics、Rename/Delete Markersメニューを
Flame 2025.2.7のMac/Linuxで確認済みと報告。以下の古い「実機未検証」はその報告前の履歴。
データ書込み／削除、新launcher、直接command、Linux Internal/Probe、branch切替の
実機動作までは確認済みとしない。詳細な両repo commit/treeを伴う実機ログは未提供。

今回の変更: shell入口でFlame 2025.2.7付属Pythonを優先し、helper読込み前にversionを検査。
checkout外の安定コピーと `dgpy-flame` を追加。起動セッション環境、VERSION照合、
bootstrap・重複・broken Probe・TOML検証を実装。既存hook、user profile、旧binを変更しない。
新binへの導入と追加実機手順は [DEV_WORKFLOW](DEV_WORKFLOW.md)。
検証結果と未確認事項は [今回の検証記録](validation/2026-10-09-launcher.md)。
ソースcommit `73ed4723a8f40bc92657a67385e8c38810cae7ff`。
macOS 26.7.1のFlame付属Python 3.11.5でPublic全88件、Internal4件とhook integration成功。
実vendor起動先と仮hookのdry-runも成功。新launcherのGUI実機検証は未実施。
CI用Python3.6.8 buildのsysconfig不足を修正した最終ソースcommit
`9d394954ad1565ac52c3fcbb5a662bd9b8de6be9` の
[CI 37913038785](https://github.com/71233/dg-python-scripts/actions/runs/37913038785)は
Linux/macOSの全suite・wheelと実Python3.6.8／3.11.5入口検証がすべてsuccess。
最新headのCIもPR checksで確認する。以降は過去のsnapshotとして扱う。

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
初回のCIはLinux上でPython 3.11のsuiteとwheelを検証した。
継続作業の変更・CI状態は下の再監査記録を参照する。

- ローカルMacのPython 3.9.6: helperのGit/symlink安全性テスト21件成功。
- ローカルMacのPython 3.12.14: Public suite 67件、Internal統合4件成功。両wheel build成功。
- CIのPython 3.11: PR checksを確認すること。
- Flame 2025.2.7 Mac/Linux実機検証: **未実施**。DEV_WORKFLOWの手順を実施して結果を追加する。
- ChatGPT Project設定: ユーザーから設置完了の報告あり。以前の「貼付が必要」は古い記録。

## 作業を終えるとき

このファイルに作業branch、PRリンク、最終検証、未解決点、次の具体的操作を更新する。
機能ごとの仕様・実測結果はFLAME_NOTES、非公開の詳細はInternalへ保存する。
GitHubで新しい変更が入ったら上記snapshotを現在値として扱わない。

Public PR #4のLinux/Python 3.11 CI成功を確認。Internal CIには既存の空Media Panel判定の
不整合があり、修正パッチと権限上の制約はInternalのDEVELOPMENTに記録した。

## 2026-10-09 継続作業の再監査

GitHubのbranch/全PR一覧とローカルコードを再取得して確認した。
開始時Public `chore/dev-workflow` / `7263696cfd53fe012e7a1ec18bb86d9317add9da`、
tree clean、GitHubのPR #4 headと一致。mainは上記snapshotと同じ。
PR #4と既存branchを再利用し、Status HUD PR #3は変更していない。

- 更新／切替計画の後に全repoを再確認。HEADだけでなくbranch、local/origin参照、trackingも確認。
  適用先を完全commitへ固定した。
- setup/statusに追加hook検索先と環境変数からの重複候補検出を追加。既存hookは変更しない。
- ローカルmacOS 26.7.1: Python 3.9.6 helper安全性29件、Python 3.12.15 Public全75件成功。
  bare repo/仮hook先のみ使用。Mac/Linux既定pathはmockで確認し、Linux実行結果とは区別する。
- CIにLinux/macOS matrixを追加。ソースcommit `9eae27315ab8669bc42e4e826231bec4082ac6a4` の
  [CI 37879066268](https://github.com/71233/dg-python-scripts/actions/runs/37879066268) が両OSで成功。
  Python 3.11全75件とwheel build成功。文書のみの追記commitはPR checksも確認する。
- 検証の対象・制約・次の操作は [検証記録](validation/2026-10-09-dev-workflow.md)。

Flame 2025.2.7は両OSとも実機未検証。PRはdraftを維持し、mergeは行わない。
次はDEV_WORKFLOWのFlame実機手順をMac/Linuxで実施し、二重登録・module path・
再起動後のbranch切替反映の結果を記録する。
