/*
 * Screaming Channels — nRF52832 DK ファームウェア
 *
 * 設定可能な BLE チャンネルで無変調 CW キャリアを送信しながら、
 * AES-128（ソフトウェア）をループ実行する。
 * ホスト PC は UART でデバイスを制御し、SDR（例: HackRF）で EM サイドチャネルを取得する。
 *
 * UART: 115200 8N1、コマンドは ASCII 1 文字 + データ
 *
 * トップレベルコマンド
 * ------------------
 *   ?        ヘルプ表示
 *   C        設定チャンネルで CW 開始
 *   S        CW 停止
 *   F<n>\n   無線チャンネル設定 0–80  (F4 → 2.404 GHz)
 *   A        AES サブモード開始 (下記参照)
 *
 * AES サブモードコマンド ('A' で入った後)
 * -----------------------------------------
 *   K        16バイト鍵を読み込む (10進スペース区切り + 改行)
 *   P        16バイト平文を読み込む
 *   N<n>\n   繰り返し回数設定 (既定値 1)
 *   R        AES を N 回実行 → 完了時に "OK\r\n" を返す
 *   O        最後の暗号文を出力 (入力と同形式)
 *   Q        AES サブモード終了
 *
 * ボード: nRF52832 DK (PCA10040)
 * SDK:   nRF5 SDK 14.2.0
 */

#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "nrf.h"
#include "nrf_delay.h"
#include "boards.h"
#include "app_uart.h"
#include "app_error.h"
#include "nordic_common.h"

#include "aes128/aes128.h"

/*
 * SDK 14 の NRF_RADIO_Type は TEST レジスタを構造体メンバとして持たない。
 * nRF52832 PS によると TEST は RADIO ベース + 0x540 にある。
 */
#define RADIO_TEST_REG              (*((volatile uint32_t *)(NRF_RADIO_BASE + 0x540u)))
#define RADIO_TEST_CONSTCARRIER_Pos 0UL
#define RADIO_TEST_CONSTCARRIER_Enabled (1UL << RADIO_TEST_CONSTCARRIER_Pos)

/* ------------------------------------------------------------------ */
/* UART 設定                                                            */
/* ------------------------------------------------------------------ */

#define TX_BUF_SZ 512u
#define RX_BUF_SZ 256u

static void on_uart_error(app_uart_evt_t *evt)
{
    if (evt->evt_type == APP_UART_COMMUNICATION_ERROR)
        APP_ERROR_HANDLER(evt->data.error_communication);
    else if (evt->evt_type == APP_UART_FIFO_ERROR)
        APP_ERROR_HANDLER(evt->data.error_code);
}

/* ------------------------------------------------------------------ */
/* 無線: 無変調定常キャリア (CW)                                        */
/* ------------------------------------------------------------------ */

static uint32_t g_channel = 4u;   /* 既定値: 2.404 GHz */
static bool     g_cw_on   = false;

static void cw_start(void)
{
    NRF_RADIO->EVENTS_DISABLED = 0u;
    NRF_RADIO->TASKS_DISABLE   = 1u;
    while (!NRF_RADIO->EVENTS_DISABLED) {}
    NRF_RADIO->EVENTS_DISABLED = 0u;

    NRF_RADIO->FREQUENCY = g_channel;
    NRF_RADIO->TXPOWER   = (uint32_t)RADIO_TXPOWER_TXPOWER_0dBm
                           << RADIO_TXPOWER_TXPOWER_Pos;
    NRF_RADIO->MODE      = (uint32_t)RADIO_MODE_MODE_Ble_1Mbit
                           << RADIO_MODE_MODE_Pos;

    /* TX 有効化の前に定常キャリアテストモードを設定する */
    RADIO_TEST_REG = RADIO_TEST_CONSTCARRIER_Enabled;

    NRF_RADIO->TASKS_TXEN = 1u;
    g_cw_on = true;
}

static void cw_stop(void)
{
    RADIO_TEST_REG               = 0u;
    NRF_RADIO->EVENTS_DISABLED   = 0u;
    NRF_RADIO->TASKS_DISABLE     = 1u;
    while (!NRF_RADIO->EVENTS_DISABLED) {}
    g_cw_on = false;
}

/* ------------------------------------------------------------------ */
/* 入出力補助関数                                                        */
/* ------------------------------------------------------------------ */

static void read_bytes16(uint8_t out[16])
{
    int v;
    for (int i = 0; i < 16; i++) {
        scanf("%d", &v);
        out[i] = (uint8_t)v;
    }
}

static void print_bytes16(const uint8_t buf[16])
{
    for (int i = 0; i < 15; i++)
        printf("%d ", buf[i]);
    printf("%d\r\n", buf[15]);
}

/*
 * SDR が AES 実行開始を検出できるよう、ビットトグルパターンを出力する。
 * volatile を付けてコンパイラの最適化除去を防ぐ。
 */
static void emit_preamble(void)
{
    volatile uint32_t x = 0u;
    for (int i = 0; i < 16; i++)
        x ^= 0xAAAAAAAAu;
    (void)x;
}

/* ------------------------------------------------------------------ */
/* AES サブモード                                                        */
/* ------------------------------------------------------------------ */

static void run_aes_mode(void)
{
    Aes128Ctx ctx;
    uint8_t key[AES128_KEY_LEN]   = {0};
    uint8_t plain[AES128_BLOCK_LEN] = {0};
    uint8_t cipher[AES128_BLOCK_LEN] = {0};
    uint32_t reps = 1u;
    bool     has_key = false;

    printf("AES mode\r\n");

    uint8_t cmd;
    bool done = false;
    while (!done) {
        scanf("%c", &cmd);
        switch (cmd) {
            case 'K':
                read_bytes16(key);
                aes128_init(&ctx, key);
                has_key = true;
                print_bytes16(key);
                break;

            case 'P':
                read_bytes16(plain);
                print_bytes16(plain);
                break;

            case 'N': {
                uint32_t n;
                scanf("%lu", &n);
                reps = n;
                printf("N=%lu\r\n", reps);
                break;
            }

            case 'R':
                if (!has_key) {
                    printf("ERR: key not set\r\n");
                    break;
                }
                for (uint32_t i = 0; i < reps; i++) {
                    memcpy(cipher, plain, AES128_BLOCK_LEN);
                    emit_preamble();
                    aes128_encrypt_block(&ctx, cipher);
                }
                printf("OK\r\n");
                break;

            case 'O':
                print_bytes16(cipher);
                break;

            case 'Q':
                done = true;
                break;

            default:
                break;
        }
    }

    printf("EXIT AES\r\n");
}

/* ------------------------------------------------------------------ */
/* ヘルプ表示                                                            */
/* ------------------------------------------------------------------ */

static void print_help(void)
{
    printf("--- Screaming Channels nRF52840 ---\r\n");
    printf("?       help\r\n");
    printf("C       CW start  (channel %lu, %lu MHz)\r\n",
           g_channel, 2400UL + g_channel);
    printf("S       CW stop\r\n");
    printf("F<n>    set channel 0-80\r\n");
    printf("A       AES sub-mode\r\n");
    printf("  AES: K=key P=plaintext N<n>=reps R=run O=output Q=quit\r\n");
}

/* ------------------------------------------------------------------ */
/* 起動処理                                                              */
/* ------------------------------------------------------------------ */

static void hfclk_start(void)
{
    NRF_CLOCK->EVENTS_HFCLKSTARTED = 0u;
    NRF_CLOCK->TASKS_HFCLKSTART    = 1u;
    while (!NRF_CLOCK->EVENTS_HFCLKSTARTED) {}
}

/* ------------------------------------------------------------------ */
/* メインループ                                                          */
/* ------------------------------------------------------------------ */

int main(void)
{
    uint32_t err;
    hfclk_start();

    const app_uart_comm_params_t uart_cfg = {
        .rx_pin_no    = RX_PIN_NUMBER,
        .tx_pin_no    = TX_PIN_NUMBER,
        .rts_pin_no   = RTS_PIN_NUMBER,
        .cts_pin_no   = CTS_PIN_NUMBER,
        .flow_control = APP_UART_FLOW_CONTROL_DISABLED,
        .use_parity   = false,
        .baud_rate    = UART_BAUDRATE_BAUDRATE_Baud115200,
    };

    APP_UART_FIFO_INIT(&uart_cfg, RX_BUF_SZ, TX_BUF_SZ,
                       on_uart_error, APP_IRQ_PRIORITY_LOWEST, err);
    APP_ERROR_CHECK(err);

    /* SDK 14 では bsp_board_init() が存在しないため LED 初期化は省略 */

    printf("\r\nReady — press ? for help\r\n");

    uint8_t cmd;
    while (true) {
        scanf("%c", &cmd);
        switch (cmd) {
            case '?':
                print_help();
                break;

            case 'C':
                cw_start();
                printf("CW ON ch=%lu (%lu MHz)\r\n",
                       g_channel, 2400UL + g_channel);
                break;

            case 'S':
                cw_stop();
                printf("CW OFF\r\n");
                break;

            case 'F': {
                uint32_t ch;
                scanf("%lu", &ch);
                if (ch <= 80u) {
                    g_channel = ch;
                    printf("CH=%lu\r\n", g_channel);
                    if (g_cw_on) { cw_stop(); cw_start(); }
                } else {
                    printf("ERR: ch must be 0-80\r\n");
                }
                break;
            }

            case 'A':
                run_aes_mode();
                break;

            default:
                break;
        }
    }
}
