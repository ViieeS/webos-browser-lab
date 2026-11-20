/* Presses keys by writing input events into an existing evdev node. On the C1 use /dev/input/event10
 * ("LGE Network Input"): the compositor reads it, while event1 ("LGE RCU") it does not open.
 * The kernel injects the events into that device, so the compositor sees real keys and passes them over Wayland.
 * Build: zig cc -target arm-linux-gnueabi.2.17 -mcpu=cortex_a7 -mfloat-abi=softfp -fPIE -pie (no -pie: segfault).
 * usage: evkeys <device> <gap ms> <key>...
 *   key: a linux/input-event-codes.h code (103 = up), "29+38" = code 38 with 29 (left ctrl) held,
 *        "w500" = wait 500 ms instead of the gap,
 *        "r8:-1" = relative axis 8 (REL_WHEEL) by -1, one wheel notch down; "r0:5" = REL_X by 5,
 *        "a960,540" = absolute pointer position (ABS_X, ABS_Y), as the Magic Remote reports it.
 * The device must report the codes in its key/rel/abs bitmaps, or the kernel drops them silently.
 */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* linux/input.h pulls asm headers the TV sysroot lacks. This is the kernel ABI struct on 32-bit ARM. */
struct input_event {
    long tv_sec, tv_usec;
    uint16_t type, code;
    int32_t value;
};
enum { EV_SYN = 0, EV_KEY = 1, EV_REL = 2, EV_ABS = 3, SYN_REPORT = 0, ABS_X = 0, ABS_Y = 1 };

static int fd;

static void emit(int type, int code, int value)
{
    struct input_event ev;
    memset(&ev, 0, sizeof ev);   /* the kernel stamps injected events itself */
    ev.type = type;
    ev.code = code;
    ev.value = value;
    if (write(fd, &ev, sizeof ev) != sizeof ev) {
        perror("write");
        exit(1);
    }
}

static void key(int code, int value)
{
    emit(EV_KEY, code, value);
    emit(EV_SYN, SYN_REPORT, 0);
}

static void sleep_ms(long ms)
{
    struct timespec ts = {ms / 1000, (ms % 1000) * 1000000L};
    nanosleep(&ts, NULL);
}

int main(int argc, char **argv)
{
    if (argc < 4) {
        fprintf(stderr, "usage: evkeys <device> <gap ms> <key>...\n");
        return 2;
    }
    fd = open(argv[1], O_WRONLY);
    if (fd < 0) {
        perror(argv[1]);
        return 1;
    }
    long gap = atol(argv[2]);
    for (int i = 3; i < argc; i++) {
        const char *a = argv[i];
        if (a[0] == 'w') {
            sleep_ms(atol(a + 1));
            continue;
        }
        if (a[0] == 'r' || a[0] == 'a') {   /* one report, then the gap */
            char *sep = strpbrk(a + 1, ":,");
            if (!sep) {
                fprintf(stderr, "bad argument %s\n", a);
                return 2;
            }
            if (a[0] == 'r') {
                emit(EV_REL, atoi(a + 1), atoi(sep + 1));
            } else {
                emit(EV_ABS, ABS_X, atoi(a + 1));
                emit(EV_ABS, ABS_Y, atoi(sep + 1));
            }
            emit(EV_SYN, SYN_REPORT, 0);
            sleep_ms(gap);
            continue;
        }
        char *plus = strchr(a, '+');
        int mod = plus ? atoi(a) : 0;
        int code = atoi(plus ? plus + 1 : a);
        if (mod)
            key(mod, 1);
        key(code, 1);
        sleep_ms(30);   /* a held press, like a person's tap */
        key(code, 0);
        if (mod)
            key(mod, 0);
        sleep_ms(gap);
    }
    close(fd);
    return 0;
}
