"""
取得済み .npy トレースを可視化するスタンドアロンスクリプト

使い方:
    uv run python3 view_traces.py traces/
    uv run python3 view_traces.py traces/ --index 5        # トレース番号を指定
    uv run python3 view_traces.py traces/ --save out.png   # 画像保存
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, filtfilt


def load_dir(traces_dir: Path):
    traces_path = traces_dir / "traces.npy"
    if not traces_path.exists():
        sys.exit(f"ERROR: {traces_path} が見つかりません")

    traces = np.load(traces_path)
    if traces.ndim == 1:
        traces = traces[np.newaxis, :]

    plaintexts = None
    keys = None
    pt_path = traces_dir / "plaintexts.npy"
    k_path = traces_dir / "keys.npy"
    if pt_path.exists():
        plaintexts = np.load(pt_path)
    if k_path.exists():
        keys = np.load(k_path)

    return traces, plaintexts, keys


def lowpass(signal, cutoff=30e3, fs=5e6, order=4):
    b, a = butter(order, cutoff / (fs / 2), btype="low")
    return filtfilt(b, a, signal)


def plot(traces, plaintexts, keys, index: int, sampling_rate=5e6, save_path=None):
    n_traces, n_samples = traces.shape
    t_us = np.arange(n_samples) / sampling_rate * 1e6

    index = min(index, n_traces - 1)
    single = traces[index]
    average = traces.mean(axis=0)

    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    fig.suptitle(
        f"Screaming Channel Traces  ({n_traces} traces × {n_samples}"
        f"samples @ {sampling_rate / 1e6:.1f} MHz)",
        fontsize=12,
    )

    # Panel 1: 指定インデックスの単一トレース
    axes[0].plot(t_us, single, color="tab:blue", linewidth=0.6)
    axes[0].set_title(f"Single trace  (index={index})")
    axes[0].set_ylabel("amplitude")
    if plaintexts is not None and index < len(plaintexts):
        pt_hex = (
            plaintexts[index].tobytes().hex()
            if plaintexts[index].dtype == np.uint8
            else ""
        )
        axes[0].set_xlabel(f"plaintext: {pt_hex}", fontsize=8)

    # Panel 2: 全トレースのオーバーレイ (最大 50 本、透明度を下げる)
    max_overlay = min(n_traces, 50)
    alpha = max(0.03, 1.0 / max_overlay)
    for i in range(max_overlay):
        axes[1].plot(t_us, traces[i], color="tab:gray", linewidth=0.4, alpha=alpha)
    axes[1].plot(
        t_us, average, color="tab:red", linewidth=1.2, label="average", zorder=10
    )
    axes[1].set_title(f"Overlay ({max_overlay} traces) + average")
    axes[1].set_ylabel("amplitude")
    axes[1].legend(loc="upper right")

    # Panel 3: 平均波形
    axes[2].plot(t_us, average, color="tab:red", linewidth=1.2)
    axes[2].set_title(f"Average of all {n_traces} traces")
    axes[2].set_ylabel("amplitude")

    # Panel 4: 平均波形をローパスフィルタで平滑化 (AES ラウンド構造を強調)
    try:
        avg_lpf = lowpass(average, cutoff=30e3, fs=sampling_rate)
    except Exception:
        avg_lpf = average
    axes[3].plot(
        t_us, average, color="tab:red", linewidth=0.8, alpha=0.4, label="average"
    )
    axes[3].plot(t_us, avg_lpf, color="tab:orange", linewidth=1.5, label="LPF 30 kHz")
    axes[3].set_title("Average + LPF (round structure)")
    axes[3].set_ylabel("amplitude")
    axes[3].set_xlabel("time [µs]")
    axes[3].legend(loc="upper right")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150)
        print(f"saved: {save_path}")
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(description="View screaming channel traces")
    parser.add_argument("traces_dir", type=Path, help="traces/ ディレクトリ")
    parser.add_argument(
        "--index",
        type=int,
        default=0,
        help="表示する単一トレースのインデックス (デフォルト 0)",
    )
    parser.add_argument(
        "--save",
        type=str,
        default=None,
        help="画像ファイルへ保存するパス (省略時は画面表示)",
    )
    parser.add_argument(
        "--fs", type=float, default=5e6, help="サンプリングレート (Hz, デフォルト 5e6)"
    )
    args = parser.parse_args()

    traces, plaintexts, keys = load_dir(args.traces_dir)
    n_traces, n_samples = traces.shape
    duration_ms = n_samples / args.fs * 1e3
    print(
        f"Loaded: {n_traces} traces × {n_samples} samples"
        f"({duration_ms:.2f} ms per trace)"
    )
    print(
        f"amplitude min={traces.min():.4f}"
        f"max={traces.max():.4f} mean={traces.mean():.4f}"
    )

    plot(
        traces,
        plaintexts,
        keys,
        index=args.index,
        sampling_rate=args.fs,
        save_path=args.save,
    )


if __name__ == "__main__":
    main()
