# ホスト (macOS / Linux) 上で aes128 ユニットテストをビルド・実行する
#
# 使い方:
#   make -C firmware/tests        # ビルドして実行
#   make -C firmware/tests clean  # 生成物を削除

CC      := cc
CFLAGS  := -std=c11 -Wall -Wextra -O2 -I../src
TARGET  := test_aes128
SRCS    := test_aes128.c ../src/aes128/aes128.c

.PHONY: all clean

all: $(TARGET)
	@echo ""
	@./$(TARGET)

$(TARGET): $(SRCS)
	$(CC) $(CFLAGS) -o $@ $^

clean:
	rm -f $(TARGET)
