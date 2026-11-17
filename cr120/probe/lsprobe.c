// Does LS2 let an unregistered root process (like content_shell) call com.webos.media?
// Registers under the given name ("" = anonymous) and calls getActivePipelines once.
// usage on the TV: ./lsprobe [service name]
#include <glib.h>
#include <luna-service2/lunaservice.h>
#include <stdio.h>

static GMainLoop *loop;

static bool on_reply(LSHandle *sh, LSMessage *msg, void *ctx) {
  printf("reply: %.200s\n", LSMessageGetPayload(msg));
  g_main_loop_quit(loop);
  return true;
}

int main(int argc, char **argv) {
  const char *name = argc > 1 && argv[1][0] ? argv[1] : NULL;
  LSError err;
  LSHandle *h = NULL;
  LSErrorInit(&err);
  loop = g_main_loop_new(NULL, FALSE);
  if (!LSRegister(name, &h, &err)) { printf("register failed: %s\n", err.message); return 1; }
  if (!LSGmainAttach(h, loop, &err)) { printf("attach failed: %s\n", err.message); return 1; }
  if (!LSCallOneReply(h, "luna://com.webos.media/getActivePipelines", "{}", on_reply, NULL, NULL, &err)) {
    printf("call failed: %s\n", err.message);
    return 1;
  }
  g_timeout_add_seconds(5, (GSourceFunc)g_main_loop_quit, loop);
  g_main_loop_run(loop);
  return 0;
}
