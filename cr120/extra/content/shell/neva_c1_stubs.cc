// content_shell links content/browser built with use_neva_appruntime, which calls into
// neva/app_runtime and the PWA manager. content_shell has neither app runtime nor webapps, so
// these keep the plain-browser behaviour: file origins named after the app id, no PWA binder.

#include "base/strings/string_util.h"
#include "extensions/shell/neva/installable_manager.h"
#include "neva/app_runtime/public/file_security_origin.h"
#include "url/origin.h"
#include "url/url_constants.h"

namespace neva_app_runtime {

std::string FileSchemeHostForApp(const std::string& app_id) {
  return base::ToLowerASCII(app_id);
}

url::Origin CreateFileSecurityOriginForApp(const std::string& app_id) {
  url::Origin origin = url::Origin::CreateFromNormalizedTuple(
      url::kFileScheme, FileSchemeHostForApp(app_id), 0);
  origin.set_webapp_id(app_id);
  return origin;
}

void InstallableManager::BindInstallableManager(
    mojo::PendingReceiver<mojom::InstallableManager> receiver,
    content::RenderFrameHost* render_frame_host) {}

}  // namespace neva_app_runtime
