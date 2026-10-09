# Flame仕様・検証記録

基準: Flame 2025.2.7 / Python 3.11 / PySide6。
2026系列は機能ごとに別の確認が必要。これはProject Instructionsへ固定しない。

## 2026-10-09 ユーザー報告と追加変更の区別

ユーザー報告: Flame 2025.2.7 Mac/LinuxでPublicメニュー、About/Diagnostics、
Rename/Delete Markersメニューが動作。LinuxのPython 3.6.8では旧shebang入口でSyntaxError、
Flame付属Python 3.11.5を明示した呼出しは成功。後者は旧helperの結果。
旧文書の包括的な「実機未検証」と食い違うため、この最新報告を明示した。
報告には検証時の両repoのfull commit/tree、全ログ、再現回数が揃っていない。
Rename書込み／Marker削除の実測、新入口・launcherの成功をこの報告から推定しない。

新実装: vendor startApplicationのVERSION=2025.2.7を照合し、論理pathを保持する。
ローカルMacの付属Python 3.11.5を実行し、vendor scriptの版情報／製品選択処理を読んだ。
Flameを起動した検証ではない。launch時のexec、子環境、hook/config拒否は仮環境のテスト。
新入口・launcherのMac/Linux GUI起動は未検証。既存実hookと共有旧DGpyは変更していない。
[検証記録](validation/2026-10-09-launcher.md) と [手順](DEV_WORKFLOW.md) を参照。
以下の「未実施」は過去作業時の記録。

## 既存コードから確認できる契約

以下は2026-10-09時点のmain `1764a9f`にある実装・テスト・コメントの整理。
今回の作業で実機を再測定した結果ではない。生ログと環境情報を伴う追加検証はInternalへ記録する。

| 項目 | 現在の契約 | 根拠 |
| --- | --- | --- |
| Selection | predicateとexecuteで対象が異なり得る。同じメンバーはpredicate順を維持。capture時に未選択のcontext対象があればpredicateを優先。それ以外の不一致はexecuteへfallback。snapshotはone-shot。 | `src/dg_python_scripts/actions/selection.py`, `SelectionBrokerTests` |
| Rename | `PyBatchIteration`はFlame管理の命名のため除外。書込み後のread-backを検証する。 | `rename.py`, `RenameTests` |
| Delete Markers | Media Panelのみ。Clip/SequenceとReelの直下clips/sequencesが対象。Folder/Library/ReelGroupは除外、再帰しない。対象自身のmarkersのみを扱う。 | `markers.py`, `delete_markers_action.py`, `test_markers.py` |
| Extensions | TOMLに列挙されたmoduleをregistry初回生成時に一度load。設定変更は再起動で確認。失敗したextensionは登録全体を反映せず隔離。 | `extensions/loader.py`, `hooks.py`, `ExtensionTests` |
| UI | Renameの現在UIと共通themeを参照基準にする。完成状態ではなくコードを参照する。 | `ui/rename.py`, `ui/theme.py` |

過去チャットの「Delete MarkersはClip/Sequenceのみ」という省略はReel対応を表現しきれていない。
新規変更では上記コードを確認する。生ログのない主張を実測の新証拠へ昇格させない。

## 開発配置・更新

symlinkで更新されるのはディスク上のファイル。import済みmoduleとregistryの更新を
メニュー再読み込みだけで保証しない。クリーンな検証にはFlame再起動を使う。
新しい補助コマンドのFlame 2025.2.7 Mac/Linux実機確認は未実施。
2026-10-09の継続作業で、仮hook先を使った重複検出とGit競合の回帰テストを追加した。
これはFlameのhook探索・menu登録の実測ではない。詳細は
[開発環境検証記録](validation/2026-10-09-dev-workflow.md)。
手順は [DEV_WORKFLOW.md](DEV_WORKFLOW.md)。

## 新しい記録の書式

- 日時、目的、OS、Flame build、Python version。
- repo / branch / full commit / dirty状態（両repoを使った場合は両方）。
- hook先、起動方法、設定（秘密情報は記載しない）。
- 操作、期待、観測、再現回数、read-only／write／deleteの区分。
- 根拠のPR・匿名化ログへのリンク、推測・未確認事項、次の検証。

社内環境・生ログはInternalへ保存。公開してよい結論だけをPublicへ転記する。
