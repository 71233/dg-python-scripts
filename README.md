# DGpy

Autodesk Flame専用のPythonツール基盤。主リポジトリは
[`71233/dg-python-scripts`](https://github.com/71233/dg-python-scripts)。
初期構成をFlame 2025.2.7および2026.2.3実機で読み込み確認済みです。


## 命名

- **表示名 / 製品名:** `DGpy`
- **GitHub / distribution名:** `dg-python-scripts`
- **Python import package:** `dg_python_scripts`
- **Flame bootstrap:** `dgpy_bootstrap.py`
- **環境変数 / Action namespace:** `DGPY_*` / `dgpy.*`
- **Internal distribution / import:** `dg-python-scripts-internal` / `dg_python_scripts_internal`

Pythonのdistribution名とimport名は同じ語をハイフン／アンダースコアで表現し、
既存の `dgpy` 名前空間とは分離します。Flame UI上では短いブランド名 `DGpy` を維持します。

## 対象と構成

- **Primary:** Flame 2025.2.7 / Python 3.11 / PySide6。
- **Future:** Flame 2026+。対応確認済みとは扱わず、実際に見つかったAPI差分だけを`compat`に追加します。
- CoreはFlame／Qtをimportせずに読み込み・テストできます。UI表示時のみPySide6を読み込みます。
- 外部Python依存はありません。Flame／PySide6はホストが提供するものを使います。

```text
bootstrap/dgpy_bootstrap.py   # Flame Hook領域に置く唯一のDGpyファイル
src/dg_python_scripts/
  __init__.py, version.py
  hooks.py                   # menu入口とCore registry
  runtime.py                 # Flame version検出
  actions/registry.py        # context対応、順序保持、重複IDを拒否
  actions/menu.py            # Flame menu辞書への共通serialize
  actions/main_menu.py       # About / Diagnostics
  ui/theme.py, about.py      # 小さなDGpyテーマと診断dialog
  config/loader.py           # defaults + optional TOML
  extensions/loader.py      # config指定moduleのgeneric loader
  compat/__init__.py         # 将来のAPI差分の置き場
tests/                       # Flame不要のunittest
```

Thin Hook / Thick Package: bootstrapはHook呼び出しを`dg_python_scripts.hooks`へ委譲します。
importやmenu構築に失敗した場合はtracebackをログに出し、空tupleを返します。
業務処理、設定、UI、Action定義はすべてpackage側へ置きます。

## 開発とテスト

Python 3.11以上を使用してください。

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

インストールせずにCoreをテストする場合:

```sh
PYTHONPATH="$PWD/src" python3.11 -m unittest discover -s tests -v
```

配布物にはpackageと`share/dg-python-scripts/bootstrap/dgpy_bootstrap.py`を含めます。
wheelの構築は`python3.11 -m pip wheel --no-deps . -w dist`で行えます。
Flame Hook領域への配置は自動で行いません。

## 開発環境の更新とFlame配置

Mac/Linux共通の `dgpy-update`、`dgpy-status`、`dgpy-switch`、`dgpy-setup` を追加しました。
既存配置と作業中の変更を保護し、必要なbootstrap／Probeだけをsymlinkします。
初回tool install、起動環境、日常操作、Probeの有効化と実機検証は
[DEV_WORKFLOW](docs/DEV_WORKFLOW.md)を参照してください。

```sh
python3 tools/dgpy_dev.py install --apply
export PATH="$HOME/DGpy/bin:$PATH"
dgpy-setup                   # まずプレビュー
dgpy-setup --apply
eval "$(dgpy-setup env)"     # 同じシェルからFlameを起動
dgpy-status
```

既定checkoutは `~/DGpy/dg-python-scripts` と `~/DGpy/dg-python-scripts-internal`。
異なる親ディレクトリは `DGPY_ROOT` または `--root` を指定します。
コード更新後はFlameを再起動して確認します。新しいsetupの実機検証は未実施です。

## 作業再開と仕様の保存先

- [Project Instructions](docs/PROJECT_INSTRUCTIONS.md): 恒久ルール。ChatGPT設定への貼付用。
- [Development](docs/DEVELOPMENT.md): 現在のbranch/PR、検証状況、次の操作。
- [Flame Notes](docs/FLAME_NOTES.md): 現在のAPI契約、証拠、未確認事項。
- Internalの同名docs: 非公開Probeの進捗と実測ログ。

作業開始時にGitHubの現在値を確認し、文書に書かれたsnapshotを現在値と取り違えないでください。

## 設定

設定なしで動作します。任意で `DGPY_CONFIG` にTOMLファイルの絶対パスを指定します。
Flame 2025.2.7のPython 3.11に含まれる標準ライブラリ `tomllib` を使うため、
設定読み込みのための外部dependencyはありません。

```toml
[ui]
menu_caption = "DGpy"

[extensions]
modules = []
```

Coreが扱う設定はCore自身の責務に限定します。

- `[ui]`: DGpy Coreの表示設定。
- `[extensions]`: 読み込むExtension module名。実際のload処理はExtension loaderで扱います。
- 社内パス、サーバー名、社内サービス設定などはCore schemaへ追加せず、internal Extension側で管理します。

未知のtable/key、空のcaption、不正なmodule名、module名の重複は明示的なエラーです。
指定ファイルの不存在やTOML構文エラーも隠さず、bootstrap境界でログに記録します。
設定の読み込みは各Flame menu hookの構築時です。

## Extension

依存方向は常に `dg-python-scripts-internal → dg-python-scripts` です。
Coreはinternal package名をハードコードせず、TOMLに指定されたPython moduleをgenericに読み込みます。

```toml
[extensions]
modules = ["dg_python_scripts_internal"]
```

Extension moduleは公開関数 `register(registry)` を1つ実装します。

```python
from dg_python_scripts.actions.registry import Action

def execute_internal_tool(selection):
    print("Internal tool")

def register(registry):
    registry.register(
        Action(
            "dgpy.internal.example",
            "Internal Tool",
            execute_internal_tool,
            contexts=("media_panel", "timeline"),
            order=100,
            minimum_version="2025.2.7",
        )
    )
```

CoreはExtensionごとに一時Registryを渡し、`register()` が最後まで成功した場合だけ
Actionを本体Registryへまとめて反映します。import失敗、contract不正、Action ID衝突、
Extension内部の例外はそのExtensionだけを無効にしてログへ記録し、DGpy Coreと他Extensionは継続します。

ExtensionはDGpy process registryの初回生成時に1回だけ読み込まれます。
`[extensions].modules` の変更を確実に反映するにはFlameを再起動してください。
この段階では自動探索やPython entry pointは使わず、明示的なTOML設定を採用します。


## CI

GitHub ActionsはPython 3.11でPublic Core単独のunit testとwheel buildを実行します。
Public sourceが`dg_python_scripts_internal`を参照しないこともテストし、
public → internal の逆依存をCIで防ぎます。Internal repoへのアクセスは行いません。

## ライセンス

ライセンスは未確定です。[LICENSE.md](LICENSE.md)に公開Coreとinternalの分離方針を記録しています。
公開リポジトリに置くことだけではOSS利用許諾になりません。
OSSリリース前に採用ライセンスと権利者を確定し、LICENSE全文とpackage metadataを更新します。

## 参照

- [Flame 2025のコンポーネント（Python 3.11.5 / PySide6）](https://help.autodesk.com/cloudhelp/2025/ENU/Flame-WhatsNew/files/What-s-New-in-Flame-Family-2025/What-s-New-in-2025/wn-2025-config-os.html)
- [Flame 2025 Python API（get_version）](https://help.autodesk.com/cloudhelp/2025/ENU/Flame-API/files/Python-API/Flame_API_Python_API_autodesk_flame_python_api_html.html)
- [Custom UI Actions（現行2026 reference）](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Python-Hooks-Reference/Flame_API_Python_Hooks_Reference_Custom_UI_Actions_html.html)
- [Hook検索先（現行2026 reference）](https://help.autodesk.com/cloudhelp/2026/ENU/Flame-API/files/Flame_API_Python_Hooks_Reference_html.html)

2025.2.7固有のHook契約の最終確認には、実機の
`/opt/Autodesk/<PRODUCT>_<VERSION>/python`内のHook定義とサンプルを使用してください。
