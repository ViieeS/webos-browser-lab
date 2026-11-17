/* Forwards one TCP port to another, a process per connection: exposes the stock browser's DevTools
 * port, which Chromium binds to 127.0.0.1 only, on the TV's LAN address (busybox nc cannot listen).
 * usage: tcprelay <listen ip> <listen port> <target port on 127.0.0.1>
 */
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

static void pump(int a, int b)
{
    struct pollfd p[2] = {{a, POLLIN, 0}, {b, POLLIN, 0}};
    char buf[65536];
    for (;;) {
        if (poll(p, 2, -1) < 0)
            return;
        for (int i = 0; i < 2; i++) {
            if (!(p[i].revents & (POLLIN | POLLHUP | POLLERR)))
                continue;
            ssize_t n = read(p[i].fd, buf, sizeof buf);
            if (n <= 0)
                return;
            for (ssize_t off = 0; off < n;) {
                ssize_t w = write(p[1 - i].fd, buf + off, n - off);
                if (w <= 0)
                    return;
                off += w;
            }
        }
    }
}

int main(int argc, char **argv)
{
    if (argc != 4) {
        fprintf(stderr, "usage: tcprelay <listen ip> <listen port> <target port>\n");
        return 2;
    }
    signal(SIGCHLD, SIG_IGN);
    int ls = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1;
    setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in la = {.sin_family = AF_INET, .sin_port = htons(atoi(argv[2]))};
    inet_pton(AF_INET, argv[1], &la.sin_addr);
    if (bind(ls, (struct sockaddr *)&la, sizeof la) || listen(ls, 8)) {
        perror("listen");
        return 1;
    }
    for (;;) {
        int c = accept(ls, NULL, NULL);
        if (c < 0)
            continue;
        if (fork() == 0) {
            close(ls);
            int t = socket(AF_INET, SOCK_STREAM, 0);
            struct sockaddr_in ta = {.sin_family = AF_INET, .sin_port = htons(atoi(argv[3]))};
            inet_pton(AF_INET, "127.0.0.1", &ta.sin_addr);
            if (connect(t, (struct sockaddr *)&ta, sizeof ta) == 0)
                pump(c, t);
            _exit(0);
        }
        close(c);
    }
}
