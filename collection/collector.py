#!/usr/bin/env python3
"""
Screaming Channels — HackRF 波形収集スクリプト (macOS, Python 3)

AES-128 を実行中の nRF52840 から、BLE チャンネル上の CW 送信時に
生じる EM サイドチャネルトレースを取得する。

依存パッケージ (README を参照してインストール):
    SoapySDR Python バインディング、pyserial、numpy、scipy

使い方:
    python3 collector.py --config config/default.json \
                         --port /dev/tty.usbmodem0010504894541 \
                         --output ./traces \
                         --num-traces 200 [--fixed-key]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np
import serial
from scipy.signal import butter, sosfilt

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

# ------------------------------------------------------------------ #
# デジタルフィルタ                                                      #
# ------------------------------------------------------------------ #


def _bandpass_sos(lo: float, hi: float, fs: float, order: int = 5):
    return butter(order, [lo / (fs / 2), hi / (fs / 2)], btype="band", output="sos")


def _lowpass_sos(cutoff: float, fs: float, order: int = 5):
    return butter(order, cutoff / (fs / 2), btype="low", output="sos")


def _normalize(values: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(values))) if len(values) else 0.0
    if peak == 0.0:
        return values
    return values / peak


def analyze_trigger(
    cfg: dict, samples: np.ndarray
) -> tuple[np.ndarray, float, np.ndarray]:
    """
    トリガ抽出用の包絡線、しきい値、AES開始候補インデックスを返す。

    ファームウェアは AES 呼び出し前にビットトグルプリアンブルを出力する。
    その EM シグネチャは、(サンプリングレート/2 + BLE チャンネルオフセット) 付近の
    バンドパス窓内に短い電力上昇として現れる。
    """
    amplitude = np.abs(samples)
    bp_sos = _bandpass_sos(
        cfg["bandpass_lower"], cfg["bandpass_upper"], cfg["sampling_rate"]
    )
    lp_sos = _lowpass_sos(cfg["lowpass_freq"], cfg["sampling_rate"])

    envelope = sosfilt(lp_sos, np.abs(sosfilt(bp_sos, amplitude)))

    threshold = envelope.mean()
    offset_samples = -int(cfg["trigger_offset"] * cfg["sampling_rate"])

    above = envelope > threshold if cfg["trigger_rising"] else envelope < threshold
    # 立ち上がりエッジ: False → True の遷移
    edges = np.where(~above[:-1] & above[1:])[0] + 1 + offset_samples
    if above[0]:
        edges = np.concatenate([[offset_samples], edges])

    return envelope, threshold, edges


def find_trigger_edges(cfg: dict, samples: np.ndarray) -> np.ndarray:
    """各 AES 実行の開始サンプルインデックスを返す。"""
    _, _, edges = analyze_trigger(cfg, samples)
    return edges


def save_waveform_plot(
    cfg: dict,
    raw: np.ndarray,
    traces: np.ndarray,
    output_file: Path,
    max_overlay_traces: int = 25,
) -> None:
    """収集波形の確認用PNGを保存する。"""
    fs = float(cfg["sampling_rate"])
    amplitude = np.abs(raw)
    envelope, threshold, edges = analyze_trigger(cfg, raw)
    trace_len = int(cfg["signal_length"] * cfg["sampling_rate"])

    fig, axes = plt.subplots(4, 1, figsize=(12, 10), constrained_layout=True)

    raw_time_ms = np.arange(len(raw)) / fs * 1e3
    axes[0].plot(raw_time_ms, _normalize(amplitude), label="capture |IQ|")
    axes[0].plot(raw_time_ms, _normalize(envelope), label="trigger envelope")
    if np.max(np.abs(envelope)) > 0:
        axes[0].axhline(
            threshold / np.max(np.abs(envelope)),
            color="tab:orange",
            linestyle="--",
            linewidth=1.0,
            label="trigger threshold",
        )
    for start in edges[:12]:
        stop = start + trace_len
        if 0 <= start < len(raw):
            axes[0].axvline(start / fs * 1e3, color="tab:red", alpha=0.45)
        if 0 <= start and stop <= len(raw):
            axes[0].axvspan(
                start / fs * 1e3, stop / fs * 1e3, color="tab:green", alpha=0.08
            )
    axes[0].set_title("Time-domain capture and trigger")
    axes[0].set_xlabel("time [ms]")
    axes[0].set_ylabel("normalized amplitude")
    axes[0].legend(loc="upper right")

    nfft = min(256, max(16, 2 ** int(np.floor(np.log2(max(16, len(amplitude) // 8))))))
    axes[1].specgram(amplitude, NFFT=nfft, Fs=fs, noverlap=nfft // 2)
    axes[1].set_title("Spectrogram")
    axes[1].set_xlabel("time [s]")
    axes[1].set_ylabel("frequency [Hz]")

    if len(traces) == 0:
        for ax in axes[2:]:
            ax.text(0.5, 0.5, "no aligned traces", ha="center", va="center")
            ax.set_axis_off()
    else:
        trace_amp = np.abs(traces)
        trace_time_us = np.arange(trace_amp.shape[1]) / fs * 1e6
        for trace in trace_amp[:max_overlay_traces]:
            axes[2].plot(trace_time_us, _normalize(trace), alpha=0.35, linewidth=0.8)
        axes[2].set_title(f"Aligned traces ({len(trace_amp)} collected)")
        axes[2].set_xlabel("time [us]")
        axes[2].set_ylabel("normalized amplitude")

        avg = trace_amp.mean(axis=0)
        std = trace_amp.std(axis=0)
        axes[3].plot(trace_time_us, _normalize(avg), color="tab:red", label="average")
        if np.max(std) > 0:
            axes[3].plot(
                trace_time_us,
                _normalize(std),
                color="tab:blue",
                alpha=0.55,
                label="std",
            )
        axes[3].set_title("Average trace")
        axes[3].set_xlabel("time [us]")
        axes[3].set_ylabel("normalized amplitude")
        axes[3].legend(loc="upper right")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_file, dpi=160)
    plt.close(fig)


# ------------------------------------------------------------------ #
# SoapySDR 経由の HackRF キャプチャ                                    #
# ------------------------------------------------------------------ #


def _set_default_soapy_plugin_path() -> None:
    if "SOAPY_SDR_PLUGIN_PATH" in os.environ:
        return

    for path in Path("/opt/homebrew/Cellar/soapyhackrf").glob(
        "*/lib/SoapySDR/modules0.8"
    ):
        os.environ["SOAPY_SDR_PLUGIN_PATH"] = str(path)
        return


class HackRFCapture:
    """同期 IQ キャプチャのための SoapySDR 薄ラッパー。"""

    def __init__(self, cfg: dict):
        self._fs = int(cfg["sampling_rate"])
        self._freq = cfg["target_freq"]
        self._gain_rf = cfg["hackrf_gain"]
        self._gain_if = cfg["hackrf_gain_if"]
        self._gain_bb = cfg["hackrf_gain_bb"]
        self._sdr: object | None = None
        self._stream = None

    def open(self) -> None:
        _set_default_soapy_plugin_path()

        try:
            import SoapySDR
            from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_RX
        except ImportError:
            sys.exit(
                "SoapySDR Python バインディングが見つかりません。\n"
                "macOS: brew install hackrf soapysdr\n"
                "その後、このPython環境で import SoapySDR が通るようにしてください。"
            )

        self._sdr = SoapySDR.Device("driver=hackrf")
        self._sdr.setSampleRate(SOAPY_SDR_RX, 0, self._fs)
        self._sdr.setFrequency(SOAPY_SDR_RX, 0, self._freq)
        self._sdr.setGain(SOAPY_SDR_RX, 0, "AMP", self._gain_rf)
        self._sdr.setGain(SOAPY_SDR_RX, 0, "LNA", self._gain_if)
        self._sdr.setGain(SOAPY_SDR_RX, 0, "VGA", self._gain_bb)
        self._stream = self._sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        self._sdr.activateStream(self._stream)

    def read(self, num_samples: int) -> np.ndarray:
        if self._sdr is None or self._stream is None:
            raise RuntimeError("HackRF stream is not open")

        buf = np.zeros(num_samples, dtype=np.complex64)
        received = 0
        deadline = time.monotonic() + max(2.0, 5.0 * num_samples / self._fs)
        while received < num_samples:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"HackRF read timeout: {received}/{num_samples} samples received"
                )
            chunk = np.zeros(num_samples - received, dtype=np.complex64)
            ret = self._sdr.readStream(self._stream, [chunk], len(chunk))
            if ret.ret > 0:
                buf[received : received + ret.ret] = chunk[: ret.ret]
                received += ret.ret
        return buf

    def close(self) -> None:
        if self._sdr and self._stream:
            self._sdr.deactivateStream(self._stream)
            self._sdr.closeStream(self._stream)
            self._stream = None


# ------------------------------------------------------------------ #
# UART プロトコル (firmware/src/main.c と対応)                          #
# ------------------------------------------------------------------ #


def _uart_send_bytes(ser: serial.Serial, data: bytes) -> None:
    """16バイトを10進スペース区切り + 改行で送信する。"""
    line = " ".join(str(b) for b in data) + "\n"
    ser.write(line.encode())


def _format_bytes16(data: bytes) -> str:
    return " ".join(str(b) for b in data)


def _uart_wait_for(ser: serial.Serial, token: str, timeout: float = 3.0) -> str:
    buf = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = ser.read(max(1, ser.in_waiting)).decode(errors="replace")
        buf += chunk
        if token in buf:
            return buf
    raise TimeoutError(f"{token!r} の受信がタイムアウトしました。受信内容: {buf!r}")


def _uart_read_bytes16(ser: serial.Serial, timeout: float = 3.0) -> bytes:
    deadline = time.monotonic() + timeout
    line = ""
    while time.monotonic() < deadline:
        chunk = ser.read(1).decode(errors="replace")
        if not chunk:
            continue

        line += chunk
        if chunk != "\n":
            continue

        text = line.strip()
        line = ""
        if not text:
            continue

        try:
            values = [int(x) for x in text.split()]
            if len(values) == 16 and all(0 <= x <= 255 for x in values):
                return bytes(values)
        except ValueError:
            continue
    raise TimeoutError("ボードからの16バイト応答がタイムアウトしました")


def _uart_set_bytes16(
    ser: serial.Serial, command: bytes, label: str, data: bytes
) -> None:
    ser.write(command)
    _uart_send_bytes(ser, data)
    echoed = _uart_read_bytes16(ser)
    if echoed != data:
        raise RuntimeError(
            f"{label}エコーが一致しません: want={_format_bytes16(data)} "
            f"got={_format_bytes16(echoed)}"
        )


def open_device(port: str) -> serial.Serial:
    ser = serial.Serial(port, 115200, timeout=0.2)
    time.sleep(0.3)
    ser.reset_input_buffer()
    ser.write(b"Q")
    time.sleep(0.1)
    ser.reset_input_buffer()
    return ser


# ------------------------------------------------------------------ #
# メイン収集ループ                                                      #
# ------------------------------------------------------------------ #


def collect(
    cfg: dict,
    port: str,
    output_dir: str,
    num_traces: int,
    fixed_key: bool,
    plot_file: str | None,
    max_attempts: int | None,
) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    sdr = HackRFCapture(cfg)
    ser: serial.Serial | None = None
    traces: list[np.ndarray] = []
    plaintexts: list[list[int]] = []
    keys_used: list[list[int]] = []
    preview_raw: np.ndarray | None = None

    try:
        sdr.open()
        # AGC が安定するまで待機
        time.sleep(float(cfg.get("drop_start", 0.05)))

        ser = open_device(port)

        # CW キャリアをオン (既定チャンネル 4 = 2.404 GHz)
        ser.write(b"C")
        _uart_wait_for(ser, "CW ON")

        # AES サブモードへ移行
        ser.write(b"A")
        _uart_wait_for(ser, "AES mode\r\n")

        # トリガあたりの繰り返し回数を 1 に固定
        ser.write(b"N1\n")
        _uart_wait_for(ser, "N=1\r\n")

        key = bytes(random.randint(0, 255) for _ in range(16))
        _uart_set_bytes16(ser, b"K", "鍵", key)

        sig_samples = int(cfg["signal_length"] * cfg["sampling_rate"])
        capture_samples = (
            int(cfg["trigger_offset"] * cfg["sampling_rate"]) + sig_samples + 512
        )
        attempt_limit = max_attempts or max(num_traces * 5, num_traces + 20)

        i = 0
        attempts = 0
        while i < num_traces and attempts < attempt_limit:
            attempts += 1
            if not fixed_key:
                key = bytes(random.randint(0, 255) for _ in range(16))
                _uart_set_bytes16(ser, b"K", "鍵", key)

            pt = bytes(random.randint(0, 255) for _ in range(16))
            _uart_set_bytes16(ser, b"P", "平文", pt)

            # AES 実行とキャプチャを同時に開始
            ser.write(b"R")
            raw = sdr.read(capture_samples)
            _uart_wait_for(ser, "OK\r\n", timeout=2.0)
            if preview_raw is None:
                preview_raw = raw

            edges = find_trigger_edges(cfg, raw)
            if len(edges) == 0:
                print(f"  [skip] attempt {attempts}: トリガが見つかりません")
                continue

            start = int(edges[0])
            if start < 0 or start + sig_samples > len(raw):
                print(f"  [skip] attempt {attempts}: ウィンドウが範囲外です")
                continue

            preview_raw = raw
            traces.append(raw[start : start + sig_samples])
            plaintexts.append(list(pt))
            keys_used.append(list(key))
            i += 1

            if i % 10 == 0 or i == num_traces:
                print(f"  収集済み {i}/{num_traces} (attempts={attempts})")

        if len(traces) < num_traces:
            print(
                f"  [warn] {len(traces)}/{num_traces} トレースのみ収集しました "
                f"(attempts={attempts})"
            )
    finally:
        if ser is not None:
            try:
                ser.write(b"Q")
                _uart_wait_for(ser, "EXIT AES", timeout=1.0)
            except TimeoutError:
                pass
            try:
                ser.write(b"S")
                _uart_wait_for(ser, "CW OFF", timeout=1.0)
            except TimeoutError:
                pass
            ser.close()
        sdr.close()

    traces_arr = np.array(traces, dtype=np.complex64)
    pt_arr = np.array(plaintexts, dtype=np.uint8)
    keys_arr = np.array(keys_used, dtype=np.uint8)

    np.save(output_path / "traces.npy", traces_arr)
    np.save(output_path / "plaintexts.npy", pt_arr)
    np.save(output_path / "keys.npy", keys_arr)

    if preview_raw is not None:
        np.save(output_path / "preview_raw.npy", preview_raw)

    if plot_file and preview_raw is not None:
        plot_path = Path(plot_file)
        if not plot_path.is_absolute():
            plot_path = output_path / plot_path
        save_waveform_plot(cfg, preview_raw, traces_arr, plot_path)
        print(f"波形プレビューを保存しました → {plot_path}")

    print(f"\n{len(traces)} トレースを保存しました → {output_path}")


# ------------------------------------------------------------------ #
# エントリポイント                                                      #
# ------------------------------------------------------------------ #


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "nRF52840 から HackRF 経由でスクリーミングチャネルトレースを収集する"
        )
    )
    parser.add_argument("--config", required=True, help="JSON 設定ファイル")
    parser.add_argument(
        "--port", required=True, help="DK のシリアルポート (例: /dev/tty.usbmodem...)"
    )
    parser.add_argument("--output", default="./traces", help="出力ディレクトリ")
    parser.add_argument("--num-traces", type=int, default=100)
    parser.add_argument(
        "--fixed-key", action="store_true", help="全トレースで同一の鍵を使用する"
    )
    parser.add_argument(
        "--plot-file",
        default="waveforms.png",
        help="波形プレビュー画像の保存先。相対パスなら出力ディレクトリ基準",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="波形プレビュー画像を生成しない",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=None,
        help="トリガ探索の最大試行回数。未指定ならトレース数から自動設定",
    )
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = json.load(f)

    collect(
        cfg,
        args.port,
        args.output,
        args.num_traces,
        args.fixed_key,
        None if args.no_plot else args.plot_file,
        args.max_attempts,
    )


if __name__ == "__main__":
    main()
