PROJECT_NAME     := screaming_channels_ble
TARGETS          := nrf52832_xxaa
OUTPUT_DIRECTORY := _build

# SDK は firmware/ 直下に同梱する。環境変数で上書き可能。
SDK ?= $(CURDIR)/nRF5_SDK_14.2.0_17b948a
SRC  := $(CURDIR)/src

$(OUTPUT_DIRECTORY)/nrf52832_xxaa.out: \
  LINKER_SCRIPT := nrf52_xxaa.ld

# ------------------------------------------------------------------ #
# ソース                                                               #
# ------------------------------------------------------------------ #
SRC_FILES += \
  $(SRC)/main.c \
  $(SRC)/aes128/aes128.c \
  $(SDK)/components/libraries/experimental_log/src/nrf_log_frontend.c \
  $(SDK)/components/boards/boards.c \
  $(SDK)/components/libraries/util/app_error.c \
  $(SDK)/components/libraries/util/app_error_weak.c \
  $(SDK)/components/libraries/util/app_util_platform.c \
  $(SDK)/components/libraries/util/nrf_assert.c \
  $(SDK)/components/libraries/fifo/app_fifo.c \
  $(SDK)/components/libraries/uart/app_uart_fifo.c \
  $(SDK)/components/libraries/uart/retarget.c \
  $(SDK)/components/libraries/balloc/nrf_balloc.c \
  $(SDK)/components/libraries/experimental_memobj/nrf_memobj.c \
  $(SDK)/components/libraries/strerror/nrf_strerror.c \
  $(SDK)/components/drivers_nrf/common/nrf_drv_common.c \
  $(SDK)/components/drivers_nrf/uart/nrf_drv_uart.c \
  $(SDK)/components/toolchain/gcc/gcc_startup_nrf52.S \
  $(SDK)/components/toolchain/system_nrf52.c \

# ------------------------------------------------------------------ #
# インクルードパス                                                      #
# ------------------------------------------------------------------ #
INC_FOLDERS += \
  $(SRC) \
  $(SRC)/aes128 \
  $(CURDIR)/config \
  $(SDK)/components \
  $(SDK)/components/boards \
  $(SDK)/components/device \
  $(SDK)/components/toolchain \
  $(SDK)/components/toolchain/gcc \
  $(SDK)/components/toolchain/cmsis/include \
  $(SDK)/components/drivers_nrf/common \
  $(SDK)/components/drivers_nrf/delay \
  $(SDK)/components/drivers_nrf/hal \
  $(SDK)/components/drivers_nrf/nrf_soc_nosd \
  $(SDK)/components/drivers_nrf/uart \
  $(SDK)/components/libraries/atomic \
  $(SDK)/components/libraries/balloc \
  $(SDK)/components/libraries/bsp \
  $(SDK)/components/libraries/experimental_log \
  $(SDK)/components/libraries/experimental_log/src \
  $(SDK)/components/libraries/experimental_memobj \
  $(SDK)/components/libraries/experimental_section_vars \
  $(SDK)/components/libraries/fifo \
  $(SDK)/components/libraries/strerror \
  $(SDK)/components/libraries/uart \
  $(SDK)/components/libraries/util \

# ------------------------------------------------------------------ #
# コンパイラフラグ                                                      #
# ------------------------------------------------------------------ #
# -O0: 中間値がメモリに残りやすく EM 漏洩が最大になる。
# -O3 に変更するとコンパイラ最適化が SNR に与える影響を計測できる。
OPT = -O0 -g3

CFLAGS += $(OPT)
CFLAGS += -DBOARD_PCA10040
CFLAGS += -DBSP_DEFINES_ONLY
CFLAGS += -DCONFIG_GPIO_AS_PINRESET
CFLAGS += -DFLOAT_ABI_HARD
CFLAGS += -DNRF52
CFLAGS += -DNRF52832_XXAA
CFLAGS += -DNRF52_PAN_74
CFLAGS += -mcpu=cortex-m4
CFLAGS += -mthumb -mabi=aapcs
CFLAGS += -Wall
CFLAGS += -mfloat-abi=hard -mfpu=fpv4-sp-d16
CFLAGS += -ffunction-sections -fdata-sections -fno-strict-aliasing
CFLAGS += -fno-builtin -fshort-enums

ASMFLAGS += -g3
ASMFLAGS += -mcpu=cortex-m4
ASMFLAGS += -mthumb -mabi=aapcs
ASMFLAGS += -mfloat-abi=hard -mfpu=fpv4-sp-d16
ASMFLAGS += -DBOARD_PCA10040
ASMFLAGS += -DBSP_DEFINES_ONLY
ASMFLAGS += -DCONFIG_GPIO_AS_PINRESET
ASMFLAGS += -DFLOAT_ABI_HARD
ASMFLAGS += -DNRF52
ASMFLAGS += -DNRF52832_XXAA
ASMFLAGS += -DNRF52_PAN_74

LDFLAGS += $(OPT)
LDFLAGS += -mthumb -mabi=aapcs -L$(TEMPLATE_PATH) -T$(LINKER_SCRIPT)
LDFLAGS += -mcpu=cortex-m4
LDFLAGS += -mfloat-abi=hard -mfpu=fpv4-sp-d16
LDFLAGS += -Wl,--gc-sections
LDFLAGS += --specs=nano.specs

LIB_FILES += -lc -lnosys -lm

.PHONY: default help

default: nrf52832_xxaa

help:
	@echo "targets: nrf52832_xxaa  flash  erase"

TEMPLATE_PATH := $(SDK)/components/toolchain/gcc

include $(TEMPLATE_PATH)/Makefile.common
$(foreach target, $(TARGETS), $(call define_target, $(target)))

# ------------------------------------------------------------------ #
# 便利ターゲット                                                        #
# ------------------------------------------------------------------ #
.PHONY: flash erase

flash: $(OUTPUT_DIRECTORY)/nrf52832_xxaa.hex
	@echo Flashing: $<
	nrfjprog -f nrf52 --program $< --sectorerase
	nrfjprog -f nrf52 --reset

erase:
	nrfjprog -f nrf52 --eraseall
