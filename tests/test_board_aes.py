#!/usr/bin/env python3
"""
ボードレベル AES 検証テスト。

nRF52840 DK に UART で接続し、既知の平文と鍵を送信して
暗号文を受け取り、Python の cryptography ライブラリ（参照実装）と照合する。

前提パッケージ:
    pip3 install pyserial cryptography

使い方:
    uv run python3 tests/test_board_aes.py --port /dev/tty.usbmodem0006823689621
    uv run python3 tests/test_board_aes.py --port /dev/tty.usbmodem... --verbose
"""

from __future__ import annotations

import argparse
import random
import sys
import time

import serial

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    sys.exit("依存パッケージが不足しています: pip3 install cryptography")


# ------------------------------------------------------------------ #
# cryptography ライブラリによる AES-128 ECB 参照実装                    #
# ------------------------------------------------------------------ #


def reference_aes128_encrypt(key: bytes, plaintext: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(plaintext) + enc.finalize()


# ------------------------------------------------------------------ #
# UART 補助関数 (firmware/src/main.c のプロトコルに対応)                #
# ------------------------------------------------------------------ #


def _send_bytes16(ser: serial.Serial, data: bytes) -> None:
    line = " ".join(str(b) for b in data) + "\n"
    ser.write(line.encode())


def _format_bytes16(data: bytes) -> str:
    return " ".join(str(b) for b in data)


def _wait_for(ser: serial.Serial, token: str, timeout: float = 3.0) -> str:
    buf = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = ser.read(max(1, ser.in_waiting)).decode(errors="replace")
        buf += chunk
        if token in buf:
            return buf
    raise TimeoutError(f"{token!r} の受信がタイムアウトしました。受信内容: {buf!r}")


def _read_bytes16(ser: serial.Serial, timeout: float = 3.0) -> bytes:
    """UART から 16個の10進整数（スペース区切り）を1行読み取る。"""
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


# ------------------------------------------------------------------ #
# テストランナー                                                        #
# ------------------------------------------------------------------ #


class BoardAesTest:
    def __init__(self, port: str, verbose: bool = False):
        self.ser = serial.Serial(port, 115200, timeout=0.2)
        time.sleep(0.3)
        self.ser.reset_input_buffer()
        self.verbose = verbose
        self._pass = 0
        self._fail = 0

        # 前のセッションが AES モード中だった場合に備えて Q で脱出してからリセット
        self.ser.write(b"Q")
        time.sleep(0.1)
        self.ser.reset_input_buffer()

        # AES サブモードへ移行
        self.ser.write(b"A")
        _wait_for(self.ser, "AES mode\r\n")

    def close(self) -> None:
        self.ser.write(b"Q")
        try:
            _wait_for(self.ser, "EXIT AES", timeout=1.0)
        except TimeoutError:
            pass
        self.ser.close()

    def _run_one(self, label: str, key: bytes, plaintext: bytes) -> bool:
        # 鍵を送信
        self.ser.write(b"K")
        _send_bytes16(self.ser, key)
        echoed_key = _read_bytes16(self.ser)
        if echoed_key != key:
            raise RuntimeError(
                f"鍵エコーが一致しません: want={_format_bytes16(key)} "
                f"got={_format_bytes16(echoed_key)}"
            )

        # 平文を送信
        self.ser.write(b"P")
        _send_bytes16(self.ser, plaintext)
        echoed_plain = _read_bytes16(self.ser)
        if echoed_plain != plaintext:
            raise RuntimeError(
                f"平文エコーが一致しません: want={_format_bytes16(plaintext)} "
                f"got={_format_bytes16(echoed_plain)}"
            )

        # AES を実行 (繰り返し1回)
        self.ser.write(b"N1\n")
        _wait_for(self.ser, "N=1\r\n")
        self.ser.write(b"R")
        _wait_for(self.ser, "OK\r\n")

        # 暗号文を読み取る
        self.ser.write(b"O")
        got = _read_bytes16(self.ser)

        want = reference_aes128_encrypt(key, plaintext)

        ok = got == want
        tag = "PASS" if ok else "FAIL"
        print(f"[{tag}] {label}")
        if not ok or self.verbose:
            print(f"       key:   {key.hex()}")
            print(f"       plain: {plaintext.hex()}")
            print(f"       want:  {want.hex()}")
            print(f"       got:   {got.hex()}")
        if ok:
            self._pass += 1
        else:
            self._fail += 1
        return ok

    # ---- FIPS 197 付録B ----
    def test_fips_b(self) -> None:
        key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        plain = bytes.fromhex("3243f6a8885a308d313198a2e0370734")
        self._run_one("FIPS-197 Appendix B", key, plain)

    # ---- FIPS 197 付録C.1 ----
    def test_fips_c1(self) -> None:
        key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        plain = bytes.fromhex("00112233445566778899aabbccddeeff")
        self._run_one("FIPS-197 Appendix C.1", key, plain)

    # ---- 全ゼロの鍵と平文 ----
    def test_all_zeros(self) -> None:
        self._run_one("all-zeros", b"\x00" * 16, b"\x00" * 16)

    # ---- 全 0xFF ----
    def test_all_ff(self) -> None:
        self._run_one("all-0xFF", b"\xff" * 16, b"\xff" * 16)

    # ---- ランダムベクタ (Python 参照実装と照合) ----
    def test_random(self, count: int = 10) -> None:
        for i in range(count):
            key = bytes(random.randint(0, 255) for _ in range(16))
            plain = bytes(random.randint(0, 255) for _ in range(16))
            self._run_one(f"random #{i + 1}", key, plain)

    def summary(self) -> int:
        total = self._pass + self._fail
        print(f"\n{self._pass}/{total} passed")
        return 0 if self._fail == 0 else 1


# ------------------------------------------------------------------ #
# エントリポイント                                                      #
# ------------------------------------------------------------------ #


def main() -> None:
    parser = argparse.ArgumentParser(
        description="nRF52840 の AES 出力を Python 参照実装と照合して検証する"
    )
    parser.add_argument(
        "--port", required=True, help="DK のシリアルポート (例: /dev/tty.usbmodem...)"
    )
    parser.add_argument(
        "--random-count",
        type=int,
        default=10,
        help="ランダムテストベクタの本数 (既定値: 10)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="全テストの鍵・平文・暗号文を表示する"
    )
    args = parser.parse_args()

    print("=== Board AES verification ===\n")
    t = BoardAesTest(args.port, verbose=args.verbose)
    try:
        t.test_fips_b()
        t.test_fips_c1()
        t.test_all_zeros()
        t.test_all_ff()
        t.test_random(args.random_count)
    finally:
        t.close()

    sys.exit(t.summary())


if __name__ == "__main__":
    main()
