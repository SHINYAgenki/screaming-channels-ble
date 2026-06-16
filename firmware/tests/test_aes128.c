/*
 * aes128_init() / aes128_encrypt_block() のホスト側ユニットテスト
 *
 * 同じ aes128.c ソースを nRF52840 向けクロスコンパイルと共用しつつ、
 * 開発マシン上（MCU 不要）でコンパイル・実行する。
 *
 * テストベクタは NIST FIPS 197 (2001年11月) より:
 *   付録B — 単一リファレンスベクタ
 *   付録C — ECB-128 追加ベクタ 3件
 *
 * ビルドと実行:
 *   make -C firmware/tests
 */

#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "../src/aes128/aes128.h"

/* ------------------------------------------------------------------ */
/* テスト基盤                                                            */
/* ------------------------------------------------------------------ */

static int g_pass = 0;
static int g_fail = 0;

static void check(const char *label,
                  const uint8_t *got, const uint8_t *want, size_t len)
{
    if (memcmp(got, want, len) == 0) {
        printf("[PASS] %s\n", label);
        g_pass++;
    } else {
        printf("[FAIL] %s\n", label);
        printf("  want: ");
        for (size_t i = 0; i < len; i++) printf("%02x ", want[i]);
        printf("\n  got:  ");
        for (size_t i = 0; i < len; i++) printf("%02x ", got[i]);
        printf("\n");
        g_fail++;
    }
}

/* ------------------------------------------------------------------ */
/* FIPS 197 付録B                                                        */
/* 鍵:      2b7e1516 28aed2a6 abf71588 09cf4f3c                        */
/* 平文:    3243f6a8 885a308d 313198a2 e0370734                        */
/* 暗号文:  3925841d 02dc09fb dc118597 196a0b32                        */
/* ------------------------------------------------------------------ */

static void test_fips197_appendix_b(void)
{
    const uint8_t key[16] = {
        0x2b,0x7e,0x15,0x16, 0x28,0xae,0xd2,0xa6,
        0xab,0xf7,0x15,0x88, 0x09,0xcf,0x4f,0x3c,
    };
    const uint8_t plain[16] = {
        0x32,0x43,0xf6,0xa8, 0x88,0x5a,0x30,0x8d,
        0x31,0x31,0x98,0xa2, 0xe0,0x37,0x07,0x34,
    };
    const uint8_t want[16] = {
        0x39,0x25,0x84,0x1d, 0x02,0xdc,0x09,0xfb,
        0xdc,0x11,0x85,0x97, 0x19,0x6a,0x0b,0x32,
    };

    Aes128Ctx ctx;
    aes128_init(&ctx, key);

    uint8_t buf[16];
    memcpy(buf, plain, 16);
    aes128_encrypt_block(&ctx, buf);

    check("FIPS-197 Appendix B", buf, want, 16);
}

/* ------------------------------------------------------------------ */
/* FIPS 197 付録C.1 (AES-128)                                           */
/* 鍵:      000102030405060708090a0b0c0d0e0f                           */
/* 平文:    00112233445566778899aabbccddeeff                           */
/* 暗号文:  69c4e0d86a7b0430d8cdb78070b4c55a                          */
/* ------------------------------------------------------------------ */

static void test_fips197_c1(void)
{
    const uint8_t key[16] = {
        0x00,0x01,0x02,0x03, 0x04,0x05,0x06,0x07,
        0x08,0x09,0x0a,0x0b, 0x0c,0x0d,0x0e,0x0f,
    };
    const uint8_t plain[16] = {
        0x00,0x11,0x22,0x33, 0x44,0x55,0x66,0x77,
        0x88,0x99,0xaa,0xbb, 0xcc,0xdd,0xee,0xff,
    };
    const uint8_t want[16] = {
        0x69,0xc4,0xe0,0xd8, 0x6a,0x7b,0x04,0x30,
        0xd8,0xcd,0xb7,0x80, 0x70,0xb4,0xc5,0x5a,
    };

    Aes128Ctx ctx;
    aes128_init(&ctx, key);

    uint8_t buf[16];
    memcpy(buf, plain, 16);
    aes128_encrypt_block(&ctx, buf);

    check("FIPS-197 Appendix C.1", buf, want, 16);
}

/* ------------------------------------------------------------------ */
/* NIST AES 既知回答テスト — ECB-128 暗号化 サンプル1                   */
/* 鍵:      00000000000000000000000000000000                           */
/* 平文:    f34481ec3cc627bacd5dc3fb08f273e6                           */
/* 暗号文:  0336763e966d92595a567cc9ce537f5e                           */
/* ------------------------------------------------------------------ */

static void test_nist_kat_1(void)
{
    const uint8_t key[16]   = { 0 };
    const uint8_t plain[16] = {
        0xf3,0x44,0x81,0xec, 0x3c,0xc6,0x27,0xba,
        0xcd,0x5d,0xc3,0xfb, 0x08,0xf2,0x73,0xe6,
    };
    const uint8_t want[16] = {
        0x03,0x36,0x76,0x3e, 0x96,0x6d,0x92,0x59,
        0x5a,0x56,0x7c,0xc9, 0xce,0x53,0x7f,0x5e,
    };

    Aes128Ctx ctx;
    aes128_init(&ctx, key);

    uint8_t buf[16];
    memcpy(buf, plain, 16);
    aes128_encrypt_block(&ctx, buf);

    check("NIST KAT ECB-128 #1", buf, want, 16);
}

/* ------------------------------------------------------------------ */
/* NIST AES 既知回答テスト — ECB-128 暗号化 サンプル2                   */
/* 鍵:      00000000000000000000000000000000                           */
/* 平文:    9798c4640bad75c7c3227db910174e72                           */
/* 暗号文:  a9a1631bf4996954ebc093957b234589                           */
/* ------------------------------------------------------------------ */

static void test_nist_kat_2(void)
{
    const uint8_t key[16]   = { 0 };
    const uint8_t plain[16] = {
        0x97,0x98,0xc4,0x64, 0x0b,0xad,0x75,0xc7,
        0xc3,0x22,0x7d,0xb9, 0x10,0x17,0x4e,0x72,
    };
    const uint8_t want[16] = {
        0xa9,0xa1,0x63,0x1b, 0xf4,0x99,0x69,0x54,
        0xeb,0xc0,0x93,0x95, 0x7b,0x23,0x45,0x89,
    };

    Aes128Ctx ctx;
    aes128_init(&ctx, key);

    uint8_t buf[16];
    memcpy(buf, plain, 16);
    aes128_encrypt_block(&ctx, buf);

    check("NIST KAT ECB-128 #2", buf, want, 16);
}

/* ------------------------------------------------------------------ */
/* 独立性確認: 異なる鍵で同一平文を暗号化したとき結果が異なること       */
/* ------------------------------------------------------------------ */

static void test_different_keys_differ(void)
{
    const uint8_t key_a[16] = {
        0x2b,0x7e,0x15,0x16, 0x28,0xae,0xd2,0xa6,
        0xab,0xf7,0x15,0x88, 0x09,0xcf,0x4f,0x3c,
    };
    const uint8_t key_b[16] = {
        0x00,0x01,0x02,0x03, 0x04,0x05,0x06,0x07,
        0x08,0x09,0x0a,0x0b, 0x0c,0x0d,0x0e,0x0f,
    };
    const uint8_t plain[16] = { 0x00 };

    Aes128Ctx ctx_a, ctx_b;
    aes128_init(&ctx_a, key_a);
    aes128_init(&ctx_b, key_b);

    uint8_t out_a[16], out_b[16];
    memcpy(out_a, plain, 16);
    memcpy(out_b, plain, 16);
    aes128_encrypt_block(&ctx_a, out_a);
    aes128_encrypt_block(&ctx_b, out_b);

    int differ = (memcmp(out_a, out_b, 16) != 0);
    if (differ) {
        printf("[PASS] different keys produce different ciphertexts\n");
        g_pass++;
    } else {
        printf("[FAIL] different keys produced identical ciphertexts\n");
        g_fail++;
    }
}

/* ------------------------------------------------------------------ */
/* メイン                                                                */
/* ------------------------------------------------------------------ */

int main(void)
{
    printf("=== aes128 unit tests ===\n\n");

    test_fips197_appendix_b();
    test_fips197_c1();
    test_nist_kat_1();
    test_nist_kat_2();
    test_different_keys_differ();

    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
