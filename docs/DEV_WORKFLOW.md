# Mac / Linux development workflow

基準はFlame 2025.2.7。補助コマンドはPOSIX shell入口でPythonを選び、Gitとstdlibで動く。
`dgpy-flame`だけがFlameを起動する。CoreとTOML検証にはPython 3.11以上が必要。
更新／切替中はFlameでDGpyを実行せず、エディタや別のGit操作も止める。

## 初回セットアップ

両OSで同じ構造を使用する。Internalの取得にはGitHubのアクセス権が必要。

```sh
mkdir -p ~/DGpy
cd ~/DGpy
git clone https://github.com/71233/dg-python-scripts.git
git clone https://github.com/71233/dg-python-scripts-internal.git
/bin/sh dg-python-scripts/tools/dgpy install --bin-dir "$HOME/DGpy/bin"
/bin/sh dg-python-scripts/tools/dgpy install --bin-dir "$HOME/DGpy/bin" --apply
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

## Python起動と既存toolの更新

入口は `#!/bin/sh`。`DGPY_PYTHON` の絶対パス指定を最優先し、未指定なら
`/opt/Autodesk/python/2025.2.7/bin/python3`、それが存在しない環境ではPATHの
`python3` を選ぶ。helperを読み込む前にPython 3.9以上か確認し、古いPythonなら
SyntaxErrorになる前にSTOPする。付属Pythonが選択されれば、OSのPython 3.6.8は使わない。
指定runtimeの失敗を別runtimeへのfallbackで隠さない。`-I`によりhelperはPYTHONPATH、
PYTHONHOME、user siteの影響を受けない。Flame用に引き継ぐ環境は別に保持する。

installはshell入口とhelperの2ファイルをcheckout外へコピーし、5つのコマンドをリンクする。
以前のbranchに戻っても実行可能。旧bin内のPython shebang版を上書きしない。
既に導入済みの場合は、今回のbranchから**新しいbinディレクトリ**へinstallする:

```sh
/bin/sh "$DGPY_ROOT/dg-python-scripts/tools/dgpy" install --bin-dir "$HOME/DGpy/bin-launcher" --apply
export PATH="$HOME/DGpy/bin-launcher:$PATH"
hash -r
dgpy-status
```

標準以外の配置では `DGPY_PYTHON=/absolute/path/to/python3` を明示できる。
`dgpy-status`は実際に選ばれたPythonのpathとversionも表示する。
ツールはuser profile、シェル設定、既存bin、共有Hookを編集しない。

## Flame専用ランチャー

自分のFlame Userを通常の手順でロードし、作業を保存してFlameを通常終了してから使う。
`dgpy-flame`はFlame Userのロード、HOME、ユーザーディレクトリの切替を行わない。

```sh
dgpy-flame --dry-run              # 起動先・hook・環境を確認するだけ
dgpy-flame                        # 現在のFlame Userで起動
# Internal READMEに従ってローカルTOMLを用意した場合
dgpy-flame --with-internal --config "$HOME/DGpy/site.toml" --dry-run
dgpy-flame --with-internal --config "$HOME/DGpy/site.toml"
```

macOSの既定は `/opt/Autodesk/flame_2025.2.7/bin/startApplication`。
Linuxは `/opt/Autodesk/.flamefamily_2025.2.7/bin/startApplication` を優先し、存在しなければ
macOSと同じ製品pathを使う。`--flame-executable` または `DGPY_FLAME_EXECUTABLE`で
別の絶対pathを指定できるが、2025.2.7製品ディレクトリの `bin/startApplication` と
隣接する `VERSION` ファイルの厳密な版一致を要求する。vendor scriptの論理pathを保持する。
子プロセスの `START_APPLICATION_FLAVOUR=flame` によりFlameFamilyの別製品選択を防ぐ。
GUI appへのopen、sudo、任意の起動引数、deprecated user指定引数は使わない。

起動前に現在のuser hookのbootstrapリンク元、有効性、重複候補、broken/unmanaged Probeを
確認する。`--hook-dir` / `--check-hook-dir` / `--probe` はsetup/statusと同様。
`--hook-dir`は**検査先指定**でありFlameの探索設定を変更しない。実際の検索先に一致させる。
追加の共有／project／version別検索先は必ず明示する。既存hookを変更せず、競合なら停止する。
別名の通常コピー、symlink子directory、未知の検索先、実際のメニュー重複は自動検出できない。
旧DGpyとの共存は実機で確認する。既存Flameプロセスの自動検出／終了はしない。

Publicのsrcを先頭、`--with-internal`時だけInternalのsrcを続け、既存PYTHONPATHを後方に維持する。
repo全体やsrcをHook検索先へ追加しない。`DL_PYTHON_HOOK_PATH`は変更しない。
`--config`を優先し、未指定なら既存 `DGPY_CONFIG`を検証して子プロセスへ渡す。
両方なければ子で未設定となる。TOMLの構文と現在のPublic checkoutのconfig schemaを確認する。
Internalはconfig指定必須。extension importの可否や登録はFlame内で別途確認する。
環境変数はこの起動セッションに限定し、親shellや通常起動へ保存しない。

従来の `dgpy-setup env` は引き続きexport表示だけを提供する。セッション用launcherではeval不要。

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

従来のPublicメニュー、About/Diagnostics、Rename/Delete MarkersメニューはMac/Linuxで
ユーザー確認済み。以下は新launcher／直接起動commandの追加検証であり、実機未検証:

1. `dgpy-status`のrepo、branch、commit、tree状態を記録する。
2. setupのpreview、apply、再applyを確認する。既存コピーを用意した仮hook先では
   setupが停止し内容が変わらないことを確認する。
3. `dgpy-flame --dry-run`、続いて `dgpy-flame` でFlameを再起動。DGpy menuが一度だけ表示されることを確認する。
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
