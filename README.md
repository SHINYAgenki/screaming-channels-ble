# screaming-channels-ble
nRF52832 DK (PCA10040) に AES-128 を実装し、HackRF で Screaming Channel 波形を取得するプロジェクトです。

## 開発経緯
マイコンなどのハードウェア上で暗号処理を行う際に漏洩するスクリーミングチャネル情報を

## 環境構築
- OS
 - M1 macbook pro で動作確認済み
- Python 3系列
- uv


## ディレクトリ構成

```
screaming-channels-ble/
├── firmware/
│   ├── src/
│   │   ├── main.c                      # UART制御 + CW送信 + AES実行
│   │   └── aes128/
│   │       ├── aes128.h
│   │       └── aes128.c                # AES-128 ECB (FIPS 197準拠)
│   ├── config/
│   │   └── sdk_config.h                # SDK 14.2 設定ファイル
│   ├── tests/
│   │   ├── test_aes128.c               # ホスト上でのCユニットテスト
│   │   └── Makefile
│   ├── nRF5_SDK_14.2.0_17b948a/        # nRF5 SDK 14.2.0 別途ダウンロード
│   └── Makefile                        # nRF52832向けクロスコンパイル
├── collection/
│   ├── collector.py                    # HackRF波形収集スクリプト (Python 3)
│   └── config/
│       └── default.json                # 収集パラメータ
└── tests/
    └── test_board_aes.py               # ボードのAES出力を検証 (Python 3)
```

---

## 1. 必要なソフトウェア (macOS)

### 1-1. ARM クロスコンパイラ

ファームウェアのビルドに必要です。

```bash
brew install --cask gcc-arm-embedded
```

インストール先: `/Applications/ArmGNUToolchain/15.2.rel1/`

> インストール後、`firmware/nRF5_SDK_14.2.0_17b948a/components/toolchain/gcc/Makefile.posix` に以下が設定済みです（変更不要）:
> ```
> GNU_INSTALL_ROOT := /Applications/ArmGNUToolchain/15.2.rel1/arm-none-eabi/bin/
> GNU_VERSION := 15.2.1
> GNU_PREFIX := arm-none-eabi
> ```

### 1-2. HackRF + SoapySDR (波形収集用)

```bash
brew install hackrf soapysdr soapyhackrf
```

接続確認:

```bash
hackrf_info
SoapySDRUtil --find
```

`SoapySDRUtil --find` で `driver = hackrf` のデバイスが表示されれば、
SoapySDR から HackRF を開けます。

### 1-3. Python パッケージ

依存パッケージは [uv](https://docs.astral.sh/uv/) で管理しています。

```bash
# uv のインストール (未導入の場合)
brew install uv

# 仮想環境の作成と依存パッケージのインストール (初回のみ)
uv sync
```

以降、通常の Python スクリプトを実行するときは `uv run` を付けます：

```bash
uv run python3 tests/test_board_aes.py --port /dev/tty.usbmodem...
```

依存パッケージは `pyproject.toml` と `uv.lock` で固定されており、`uv sync` で誰でも同じ環境を再現できます。

### 1-4. SDR 収集時の Python と SoapySDR

通常開発と AES 検証は `.python-version` の Python 3.12.13 を使います。

ただし Homebrew の `soapysdr` は Python バインディングを
Homebrew の `python@3.14` 向けにインストールするため、HackRF 収集時だけ
`uv run --python 3.14` と `PYTHONPATH` を使います。

```bash
export PYTHONPATH="$(brew --prefix soapysdr)/lib/python3.14/site-packages:$PYTHONPATH"

# 動作確認
uv run --python 3.14 python -c "import SoapySDR; print('SoapySDR OK')"
```

SoapyHackRF のプラグインパスは `collector.py` が Homebrew の標準配置から自動検出します。
もし `SoapySDR::Device::make() no match` が出る場合は、以下も設定してください。

```bash
export SOAPY_SDR_PLUGIN_PATH="$(brew --prefix soapyhackrf)/lib/SoapySDR/modules0.8"
```

---

## 2. ファームウェアのビルド

SDK は `firmware/nRF5_SDK_14.2.0_17b948a/` に同梱済みです。

```bash
make -C firmware
```

成功すると `firmware/_build/nrf52832_xxaa.hex` が生成されます。

---

## 3. ファームウェアの書き込み

PCA10040 DK を USB で Mac に接続すると、`/Volumes/JLINK/` という仮想ドライブとしてマウントされます。

```bash
cp firmware/_build/nrf52832_xxaa.hex /Volumes/JLINK/
```

コピー完了後、ボードが自動的にリセットしてファームウェアが起動します。

> **補足: nrfjprog について**
>
> Nordic nRF Command Line Tools をインストールすると `nrfjprog` コマンドが使えますが、
> Segger J-Link ソフトウェア (`libjlinkarm.dylib`) を別途インストールしないと
> 以下のエラーが出て使用できません:
> ```
> ERROR: The nrfjprog DLL could not find the JLINK DLL.
> ```
> `/Volumes/JLINK/` へのコピーで問題なく書き込めるため、`nrfjprog` は使用しません。

---

## 4. UART でのボード操作

### 接続

```bash
# シリアルポートを確認
ls /dev/tty.usbmodem*

# 接続 (ポート名は環境により異なる)
screen /dev/tty.usbmodem0006823689621 115200
```

接続すると以下が表示されます:

```
Ready — press ? for help
```

### screen の終了方法

| 操作 | 動作 |
|---|---|
| `Ctrl+A` → `K` → `y` | screen を終了 |
| `Ctrl+A` → `d` | デタッチ (バックグラウンドで継続) |

### ボードのリセット

ループや予期しない動作が起きた場合は、PCA10040 基板上の **RESET ボタン**を押してください。

### トップレベルコマンド

| コマンド | 動作 |
|---|---|
| `?` | ヘルプ表示 |
| `C` | CW 送信開始 (既定: ch4 = 2.404 GHz) |
| `S` | CW 送信停止 |
| `F<n>` + Enter | チャンネル設定 (0–80) |
| `A` | AES サブモード開始 |

### AES サブモードコマンド (`A` で入った後)

| コマンド | 動作 |
|---|---|
| `K` + 16バイト | 鍵設定 (10進スペース区切り + 改行) |
| `P` + 16バイト | 平文設定 |
| `N<n>` + Enter | 繰り返し回数設定 |
| `R` | AES 実行 → `OK` を返す |
| `O` | 最後の暗号文を出力 |
| `Q` | AES サブモード終了 |

---

## 5. テスト

### テスト 1: C 単体テスト（ハードウェア不要）

AES-128 実装が FIPS 197 テストベクタを満たすか確認します。

```bash
make -C firmware/tests
```

期待される出力:

```
=== aes128 unit tests ===

[PASS] FIPS-197 Appendix B
[PASS] FIPS-197 Appendix C.1
[PASS] NIST KAT ECB-128 #1
[PASS] NIST KAT ECB-128 #2
[PASS] different keys produce different ciphertexts

5 passed, 0 failed
```

### テスト 2: ボード AES 検証テスト（PCA10040 DK 必要）

ボード上の AES 出力を Python 参照実装と照合します。

```bash
python3 tests/test_board_aes.py --port /dev/tty.usbmodem0006823689621
```

| オプション | 説明 | 既定値 |
|---|---|---|
| `--port` | シリアルポート（必須） | — |
| `--random-count N` | ランダムテストベクタ本数 | `10` |
| `--verbose` | 全テストの詳細表示 | なし |

---

## 6. 波形収集

HackRF と PCA10040 DK を接続し、以下を実行します:

```bash
PYTHONPATH="$(brew --prefix soapysdr)/lib/python3.14/site-packages:$PYTHONPATH" \
uv run --python 3.14 python collection/collector.py \
    --config collection/config/default.json \
    --port /dev/tty.usbmodem0006823689621 \
    --output ./traces \
    --num-traces 200
```

収集結果:

| ファイル | 内容 |
|---|---|
| `traces/traces.npy` | `(N, samples)` の複素 IQ データ |
| `traces/plaintexts.npy` | `(N, 16)` の平文バイト列 |
| `traces/keys.npy` | `(N, 16)` の鍵バイト列 |
| `traces/preview_raw.npy` | トリガ確認用の生 IQ キャプチャ |
| `traces/waveforms.png` | 収集波形の確認画像 |

`waveforms.png` には以下が表示されます:

- 生キャプチャ振幅とトリガ包絡線
- スペクトログラム
- 切り出し済みトレース
- 平均トレース

### 波形プレビュー関連オプション

| オプション | 説明 | 既定値 |
|---|---|---|
| `--plot-file PATH` | 波形プレビュー画像の保存先。相対パスなら出力ディレクトリ基準 | `waveforms.png` |
| `--no-plot` | 波形プレビュー画像を生成しない | なし |
| `--max-attempts N` | トリガ探索の最大試行回数 | 自動 |

### 収集設定パラメータ (`collection/config/default.json`)

| パラメータ | 説明 |
|---|---|
| `target_freq` | SDR 受信中心周波数 (Hz)。BLE ch4 の高調波 2.528 GHz が既定 |
| `sampling_rate` | サンプリングレート (Hz) |
| `hackrf_gain` / `_if` / `_bb` | HackRF のゲイン設定。SoapyHackRF では `AMP` / `LNA` / `VGA` に対応 |
| `bandpass_lower/upper` | トリガ検出用バンドパス周波数 (Hz) |
| `signal_length` | 1トレースあたりのキャプチャ時間 (秒) |
| `trigger_offset` | トリガ位置のオフセット (秒) |

---

## 補足: 最適化フラグと漏洩量

`firmware/Makefile` の `OPT` 変数で AES の EM 漏洩特性が変わります。

| フラグ | 特徴 |
|---|---|
| `-O0` (既定) | 中間値がメモリに残りやすく EM 漏洩が大きい |
| `-O3` | コンパイラ最適化が強く、漏洩パターンが変わる |
