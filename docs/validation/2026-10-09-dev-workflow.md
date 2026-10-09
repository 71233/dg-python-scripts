# 開発環境補助の継続検証 — 2026-10-09 JST

対象: [PR #4](https://github.com/71233/dg-python-scripts/pull/4)、branch `chore/dev-workflow`。
開始時commit `7263696cfd53fe012e7a1ec18bb86d9317add9da`、tree clean、GitHub head一致。
以下のローカル検証はこのcommitにPRの継続修正を加えたworking treeを対象とした。
最終ソースcommitとCI結果はこの記録の追記とPR checksを参照する。

OS: macOS 26.7.1 / build 25G241。Python: 3.9.6、3.12.15。
Flame: 対象2025.2.7、今回起動・実機操作なし。実際のhook配置は変更なし。

| 検証 | 観測 |
| --- | --- |
| Python 3.9.6 helper suite | 29件成功 |
| Python 3.12.15 Public suite | 75件成功 |
| Python 3.12.15 wheel build | Public wheel成功。build依存は一時directoryへ取得し、既存Python環境は変更なし |
| Git更新・切替 | 一時bare originとcloneでfast-forward、新規／既存branch切替が成功 |
| 保護条件 | dirty/untracked、ahead/diverged、detached、Git操作中、ignored衝突、異なるupstream、不存在branchで停止 |
| 確認中の外部操作 | 同じcommitの別branch切替、origin参照の変更、第二repoへの編集で停止し第一repoを変更しない |
| 仮hook配置 | preview/apply/再apply、通常ファイル・壊れたリンク・Probe競合の保護に成功 |
| 重複候補 | 追加検索先の同名コピー、別名symlink、環境変数で指定したrootのnested hookでsetup停止・既存hook保存 |
| 無関係のhook | setup成功、既存内容保存 |
| 既定hook先 | Mac/Linuxのplatform/homeをmockして仮pathで確認。Linuxの実行証拠ではない |

テストはユーザーの検索path環境を分離して実施する。実環境のhook存在に依存しない。
Linux/macOS CIのPython 3.11、wheel build結果は最終headのchecksで別途確認する。

制約: 複数repoはatomicではない。helper以外のGit/編集をロックしないため、更新中は止める。
重複検索は指定rootの保守的検査であり、全Flame検索先の自動探索ではない。
別名の通常コピー、symlinkされた子directory、Flame内での二重登録は未確認。

次の操作: DEV_WORKFLOWのFlame実機手順をMac/Linuxで実施し、repo/branch/full commit/tree、
OS/Flame/Python版、module path、menu回数、再起動後の反映を記録する。
非公開環境・ログはInternalだけに置く。

## GitHub CIの観測

検証したソースcommit: `9eae27315ab8669bc42e4e826231bec4082ac6a4`。
[CI 37879066268](https://github.com/71233/dg-python-scripts/actions/runs/37879066268) の
ubuntu-24.04 / macos-15がともにsuccess。Python 3.11 unit testとwheel buildの各stepもsuccess。
Linux job logでは75件成功を確認した。CIはFlameなしの仮repo/仮hook検証である。

Public/Internalともソース修正を既存PRへ反映し、ローカルは公開済みcommitとtree一致を
検証して同期、cleanを確認した。この追記は文書のみで、上記ソースの追加変更はない。
