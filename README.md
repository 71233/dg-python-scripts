# DGpy

Autodesk Flame専用のPythonツール基盤。主リポジトリは
[`71233/dg-python-scripts`](https://github.com/71233/dg-python-scripts)。
現在は初期構成であり、Flame実機での検証・本番導入はまだ行っていません。


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
  actions/registry.py        # 順序保持、重複IDを拒否
  actions/main_menu.py       # About / Diagnosticsとmenu生成
  ui/theme.py, about.py      # 小さなDGpyテーマと診断dialog
  config/loader.py           # defaults + optional JSON
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

## Flameでの初回確認

開発時は、Flame起動前の環境に以下を追加します。
`/absolute/path/dg-python-scripts`を実際のcheckoutの絶対パスへ置き換えてください。

```sh
export PYTHONPATH="/absolute/path/dg-python-scripts/src${PYTHONPATH:+:$PYTHONPATH}"
```

その後、`bootstrap/dgpy_bootstrap.py` **だけ**を既存のFlame Hook検索先へコピーします。
ユーザー用の代表例はLinuxの`~/flame/python`、macOSの
`~/Library/Preferences/Autodesk/flame/python`です。必要に応じてディレクトリを作成します。
開発用の代替として`DL_PYTHON_HOOK_PATH`にcheckoutの`bootstrap`ディレクトリを追加できます。
コピーと検索パス追加を同時に使って、同じbootstrapを二重に読み込まないでください。
checkout全体や`src`をHook検索先へ置かないでください。

通常のシェル環境ではなく、実際にFlameを起動するプロセスへ環境変数が渡る必要があります。
本番ではFlame用Python環境へのpackage配置または管理された`PYTHONPATH`を使用します。
この初期構成にはinstaller／updaterは含めません。

Flame再起動後、Main Menuの`DGpy → About / Diagnostics`を開きます。
DGpy version、Flame version、Python version、runtime分類が表示されます。
`primary`は検出されたversionが2025.2.7であるという意味で、実機検証済みの証明ではありません。
それ以外のFlameは`unvalidated`、Flame外は`outside-flame`になります。
診断Actionは互換性確認用に他versionでも表示します。将来の処理Actionは個別に対応範囲を定めます。

### 実機チェック（未実施）

1. Flame 2025.2.7でDGpy menuが一度だけ表示される。
2. About / Diagnosticsが開き、versionと`primary`表示を確認できる。
3. Closeで閉じ、再度開ける。既存のFlame操作に影響しない。
4. packageパスを外した場合、DGpy menuだけが表示されずログに原因が残る。

## 設定

設定なしで動作します。任意で`DGPY_CONFIG`をJSONファイルの絶対パスへ設定できます。

```json
{"menu_caption": "DGpy"}
```

現在の設定項目は`menu_caption`のみです。未指定はdefaultを使用します。
指定ファイルの不存在、JSON不正、未知のkey、空captionは明示的なエラーとし、
bootstrap境界でログに記録します。設定の読み込みはmenu構築時です。

## Extensionへの入口

依存方向は`dg-python-scripts-internal → dg-python-scripts`のみです。
Coreはinternal packageの存在、サービス、設定を知りません。
この段階では自動探索、entry point、extension lifecycleを実装しません。
明示的な登録の最小入口は次のとおりです。

```python
# 将来のExtension側のコード例（Coreはこのmoduleをimportしない）
from dg_python_scripts.actions.registry import Action
from dg_python_scripts.hooks import get_registry

def execute_internal_tool(selection):
    print("Internal tool")

def register_actions(registry):
    registry.register(Action(
        "dg_python_scripts_internal.example", "Internal Tool", execute_internal_tool
    ))

# Extension側の起動処理から一度だけ呼ぶ。
# Flameのmain thread上で、menuが構築される前に登録する。
register_actions(get_registry())
```

callbackは選択オブジェクトのtupleを受け取ります。IDはExtensionごとのnamespaceを使います。
重複IDは上書きせず拒否します。Coreのbuiltin登録は繰り返しのmenu取得でも増殖しません。
この登録APIは0.1段階の暫定APIです。実際のinternal Extension導入時に起動順序と契約を検証します。

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
