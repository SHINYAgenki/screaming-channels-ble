#pragma once

#include <stdint.h>

#define AES128_BLOCK_LEN   16u
#define AES128_KEY_LEN     16u
#define AES128_SCHED_LEN  176u   /* ラウンド鍵 11本 × 16バイト */

/*
 * aes128_init() が生成したラウンド鍵スケジュールを保持する構造体
 */
typedef struct {
    uint8_t sched[AES128_SCHED_LEN];
} Aes128Ctx;

/*
 * 16バイトの鍵 `key` を展開し、ラウンド鍵を `ctx` に格納する
 * aes128_encrypt_block() を呼ぶ前に必ず一度呼び出すこと
 */
void aes128_init(Aes128Ctx *ctx, const uint8_t key[AES128_KEY_LEN]);

/*
 * 16バイトのブロックを `ctx` のラウンド鍵で直接（インプレース）暗号化する
 * ECB モードのみ対応。他のモードが必要な場合は呼び出し側で実装すること
 */
void aes128_encrypt_block(const Aes128Ctx *ctx, uint8_t block[AES128_BLOCK_LEN]);
