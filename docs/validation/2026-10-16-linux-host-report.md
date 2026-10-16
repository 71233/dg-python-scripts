# 2026-10-16 Linux Flame 2025.2.7 — ユーザー報告

## 根拠と対象

2026-10-16に受領したユーザー報告を記録する。2台目のLinuxワークステーションでの
Flame 2025.2.7確認であり、この記録作業でエージェントがLinux実機を直接測定した結果ではない。
端末名・社内パス・ホスト・非公開ログは掲載しない。

| 環境項目 | 報告内容・制約 |
| --- | --- |
| OS | Linux。ディストリビューション・OS buildは未提供 |
| Flame | 2025.2.7。追加のbuild情報は未提供 |
| Python | Flame付属Python 3.11.5の自動選択成功との報告 |
| 実機のrepo | `71233/dg-python-scripts` |
| 実機のbranch / full commit / Git tree / dirty状態 | 未提供。記録作業時のheadで代用しない |
| hook先 / module.__file__ / 再現回数 / コンソール全文 | 未提供 |

## 報告された操作と結果

| 操作 | 結果（ユーザー報告） | 確認範囲 |
| --- | --- | --- |
| `dgpy-status` を直接実行 | 成功。Flame付属Python 3.11.5を自動選択 | 直接入口・runtime選択 |
| `dgpy-flame --dry-run` | 成功 | 起動前検査。GUI起動とは別の操作 |
| `dgpy-flame` | GUI起動・Public基本動作成功 | 基本動作の個別操作一覧は未提供 |
| 設定を指定したExtension起動 | 起動・基本動作成功 | 非公開の設定・環境情報は掲載しない |

これは報告の要約であり、コンソール出力の引用ではない。成功メッセージ、exit code、
メニューの個数、処理対象数、module path、反復回数などを補っていない。
Renameの実書込み、Delete Markersの実削除、Probeは**未検証**。
GUI・基本動作成功をデータ変更の成功へ拡張しない。

## 文書・コードとの整合

10月9日の「新入口・launcherのGUI実機動作は未検証」は、その時点の履歴。
今回のLinux報告で上記の範囲を更新する。Macの新launcher GUI、branch切替後の反映、
User切替、全hook根での重複の有無や旧Hook共存の詳細検証までは確認済みにしない。
コード上はshell入口がFlame付属Pythonを優先し、launcherがVERSION照合・hook/config検査の後に
子環境でvendor launcherを実行する。コード確認とユーザー報告は別の根拠として扱う。

## 記録作業のsnapshot（実機の検証版ではない）

Public `71233/dg-python-scripts` / `chore/dev-workflow`、開始commit
`2044d2e4c0bee925646546fa56ebb13ec4437c59`、Git tree
`912b1ba64dae7a13d50d92871aa44b92ac507ebd`、working tree clean。
GitHubの[Draft PR #4](https://github.com/71233/dg-python-scripts/pull/4) headと一致。
mainは `1764a9f258f4f9e788652a9ba37a9864dfcfdb15`。
今回の差分は文書のみ。Hook・旧bin・Flame Userは変更していない。Draft・未mergeを維持する。
10月9日の自動テスト・CI根拠は[前回記録](2026-10-09-launcher.md)を参照。

## 残タスクと次の操作

- 次の実機確認時に、使用したrepoのbranch/full commit/Git tree/dirty状態、OS build、
  Flame/Python版、起動方法、module.__file__、操作と再現回数を取得する。
- Rename書込み・Marker削除は使い捨てデータで個別検証し、Probeも別項目で記録する。
- Mac新launcher GUI、親shell・通常起動の環境維持、User切替、hook二重登録、
  branch切替とFlame再起動後の反映を確認する。

手順は[DEV_WORKFLOW](../DEV_WORKFLOW.md)。上記の未検証項目を完了扱いにせず、両PRはDraftのまま維持する。

## 記録作業で直接実行した確認

macOS 26.7.1 / build 25G241、Flame 2025.2.7付属Python 3.11.5で実行。
上記の開始commitに今回の文書差分のみを加えたworking treeを使用し、実装・テストコードは未変更。
Public unittest全88件成功（63.069秒）、Internal unittest全4件成功（0.120秒）、
TOML指定のPublic/Internal hook integration成功。文書の相対リンクと差分の空白検査も成功。
これらはローカル自動テストであり、LinuxのFlame GUI直接実測ではない。
