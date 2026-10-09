# Mac / Linux development workflow

基準はFlame 2025.2.7。補助コマンドはOSのPython 3.9以上とGitだけで動く。
CoreテストにはPython 3.11以上が必要。コマンドはFlameを起動・終了しない。
更新／切替中はFlameでDGpyを実行せず、エディタや別のGit操作も止める。

## 初回セットアップ

両OSで同じ構造を使用する。Internalの取得にはGitHubのアクセス権が必要。

```sh
mkdir -p ~/DGpy
cd ~/DGpy
git clone https://github.com/71233/dg-python-scripts.git
git clone https://github.com/71233/dg-python-scripts-internal.git
python3 dg-python-scripts/tools/dgpy_dev.py install --bin-dir "$HOME/DGpy/bin"
python3 dg-python-scripts/tools/dgpy_dev.py install --bin-dir "$HOME/DGpy/bin" --apply
export PATH="$HOME/DGpy/bin:$PATH"
export DGPY_ROOT="$HOME/DGpy"
```

この変更のPRを試す間はPublicの該当PR branchをcheckoutしてからinstallする。
`PATH`と`DGPY_ROOT`は必要ならシェル設定に自分で追記する。
ツールはcheckout外へコピーされるため、ツール導入前のbranchにも切替可能。
ツールの更新時は新しいbinディレクトリへinstallし、PATHを更新する。
異なる内容の既存ツールを上書きしない。

```sh
dgpy-setup                 # 配置のプレビュー
dgpy-setup --apply         # bootstrapへのsymlinkだけを作成
dgpy-status
```

既定のユーザーhook先:

- macOS: `~/Library/Preferences/Autodesk/flame/python`
- Linux: `~/flame/python`

異なる場所は `--hook-dir /absolute/path` で指定する（statusにも同じ指定を渡す）。
既存の通常ファイル・ディレクトリ・別リンク・壊れたリンクがあれば停止。
リンク元も同じで有効なsymlinkだけは再実行を許容する。
既存配置を移行する場合は、元ファイルを**全hook検索先の外**へ退避してから再実行する。
退避先、元パス、内容のchecksumを作業記録に残す。hook先に `.py` のバックアップを置かない。
共用・project・version別hook先、`DL_PYTHON_HOOK_PATH`にも同じbootstrapがないか確認する。
setup/statusは指定hook先、その配下、`DL_PYTHON_HOOK_PATH`、繰り返し指定できる
`--check-hook-dir` を保守的に検索する。同名bootstrap／明示Probe、別名でも同じsourceを
指すsymlinkがあれば重複候補としてsetupを停止し、statusは終了コード1で報告する。
既存hookの削除・移動は行わない。例:

```sh
dgpy-setup --check-hook-dir /path/to/shared/hooks --check-hook-dir /path/to/project/hooks
dgpy-status --check-hook-dir /path/to/shared/hooks --check-hook-dir /path/to/project/hooks
```

検索対象外のFlame設定、別の名前の通常コピー、symlinkされた子ディレクトリ、
Flameプロセスは自動検出しない。共有／project／version別検索先を明示して確認し、
Flame内でメニューが一度だけ表示されることも確認する。

## Flame起動環境

symlinkだけではpackageをimportできない。起動するプロセスへPYTHONPATHを渡す。

```sh
eval "$(dgpy-setup env)"
# 同じシェルから対象のFlame startApplicationを起動する
```

Internalを使う場合は、ローカルTOMLを用意して明示的に指定する。

```sh
# Internal READMEの設定例に従って ~/DGpy/site.toml を用意
eval "$(dgpy-setup env --with-internal --config "$HOME/DGpy/site.toml")"
```

`env`はshell exportを表示するだけで設定ファイルやシェル設定を書き換えない。
既存PYTHONPATHを後ろへ維持する。macOSのGUIから起動したFlameにはこのシェル環境が
伝わるとは限らないため、同じシェルから起動するか、管理された起動設定を使用する。
不要になった以前のcheckoutのPYTHONPATHは手動で取り除き、Flame内のmodule.__file__で確認する。
Hook検索パスへsrcやrepo全体を追加しない。

## 日常操作

```sh
dgpy-status                            # 両repo、branch、完全commit、dirty/clean、upstream
dgpy-update                            # 現在branchを両repoでfetch + fast-forward
dgpy-update --repo public               # 公開側だけ
dgpy-switch --repo public feature/example
dgpy-switch --repo internal test/example
```

`--root /path/to/DGpy`で別のcheckout親ディレクトリを指定できる。
Publicだけを取得した環境ではupdate/statusに `--repo public` を指定する。
`switch`は `--repo` を必須とし、同じbranchを両repoで使う場合だけ `--repo all` とする。
存在するorigin branchを選ぶ。branchを推測して自動作成しない。
`status`のahead/behindは最後のfetch時点で、ネットワークへ接続しない。
未配置・競合・壊れたhookはstatusの終了コード1で報告する。

安全条件:

- tracked/untrackedの変更、detached HEAD、Git操作中、index lockなら停止する。
- ignoredファイルも切替先のtrackedファイルと衝突すれば停止する。
- updateはoriginをtrackingする現在branchだけを更新する。
- switchの既存local branchは同名origin branchのtrackingを要求する。
- localがahead／diverged、origin branchが不存在／削除済みなら停止する。
- reset、stash、rebase、force checkout、force pushはしない。
- 全対象を事前確認してからworking treeを変更する。fetchはremote参照を変更し得る。
- 全repoの計画作成後、dirty状態・現在branch・HEAD・切替先local/origin参照・trackingを
  再確認する。適用先は確認済みの完全commitに固定し、確認中のbranch/ref変更なら停止する。
- 同じrootの補助コマンドによるupdate/switch同時実行をロックする。
- **複数repoの更新はトランザクションではない**。途中のディスク障害や外部Git操作で
  一方だけ更新される場合はstatusで結果を確認する。自動rollbackで変更を消さない。

更新はディスク上の変更。Flameがimport済みのpackageは自動更新されない。
メニュー再読み込みだけを完全な反映の保証とせず、検証前にFlameを再起動する。
以前のcommitへ戻す場合も、まず専用の検証branchをGitで用意してそのbranchを切り替える。
この補助ツールは任意commitへの強制resetを提供しない。

## Probeだけを有効化

Internalで該当branchを選んでから、必要な**1ファイル**を明示する。

```sh
dgpy-switch --repo internal test/example
dgpy-setup --probe "$DGPY_ROOT/dg-python-scripts-internal/experiments/dgpy_example_probe.py"
dgpy-setup --probe "$DGPY_ROOT/dg-python-scripts-internal/experiments/dgpy_example_probe.py" --apply
dgpy-status --probe "$DGPY_ROOT/dg-python-scripts-internal/experiments/dgpy_example_probe.py"
```

Probeごとのread-only／write／delete区分と使い捨て対象はInternalの文書に従う。
experiments全体をhookパスへ追加しない。Probeを無効化する際は、statusで対象が自分の
作成したsymlinkであることを確認して**そのリンクだけ**を取り除き、Flameを再起動する。
branchを戻す前に不要なProbeリンクを外す。存在しなくなったリンク元はstatusでbrokenとなる。
通常ファイルやリンク元のProbe自体を削除しない。

## 検証

```sh
PYTHONPATH=src python3.11 -m unittest discover -s tests -v
```

自動テストは一時bare repo・cloneと仮hook先で実施し、ユーザーのFlame配置を変更しない。
Linux/Mac CIとローカルMacの検証を区別して `docs/DEVELOPMENT.md` に結果を記録する。

Flame 2025.2.7のMac/Linuxそれぞれで次を行う（この変更の実機検証は未実施）:

1. `dgpy-status`のrepo、branch、commit、tree状態を記録する。
2. setupのpreview、apply、再applyを確認する。既存コピーを用意した仮hook先では
   setupが停止し内容が変わらないことを確認する。
3. 起動環境を設定してFlameを再起動。DGpy menuが一度だけ表示されることを確認する。
4. Flame consoleで `import dg_python_scripts; print(dg_python_scripts.__file__)` を実行し、
   意図したcheckoutのsrcが読み込まれたことを確認する。
5. About / Diagnostics、Rename、Delete Markersを使い捨てデータで確認する。
6. Internal diagnosticsをTOMLで有効にし、一度だけ登録されることを確認する。
7. read-only Probeを1つ有効化し、再起動後に出力とcommitを記録する。不要なリンクを外す。
8. dirty状態でupdate/switchが停止することを仮cloneで確認する。
9. 別branchへ切替→再起動→moduleパスと機能→元branchへ戻して再起動を確認する。

OS、Flame/Python版、両repoのcommit、起動方法、hook先、期待値、実際の結果、
匿名化したログ、未確認事項を記録する。実機確認前は「対応済み」としない。

公式のhook先資料は [Autodesk Python Hooks Reference](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Flame_API_Python_Hooks_Reference_html.html)
を参照。現行2026資料のため、2025.2.7実機のhook定義・設定で最終確認する。
