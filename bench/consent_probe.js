// Consent state of the current page, as the page's own consent platform (CMP) records it, plus what is on screen.
// Evaluated over CDP in the page's main world; the result is one JSON object (bench/consent_run.py).
// The verdict comes from the CMP's own record, not from the banner being gone: a hidden banner leaves no record.
(async () => {
  const r = {url: location.href};
  const vis = e => {
    const b = e.getBoundingClientRect(), s = getComputedStyle(e);
    return b.width > 50 && b.height > 30 && s.visibility !== "hidden" && s.display !== "none" && +s.opacity > 0.05;
  };
  // the banner containers of the common CMPs (and two sites' own banners)
  const SEL = {
    onetrust: "#onetrust-banner-sdk, #onetrust-consent-sdk .otPcCenter",
    cookiebot: "#CybotCookiebotDialog",
    didomi: "#didomi-popup, #didomi-notice",
    sourcepoint: "div[id^='sp_message_container'], iframe[id^='sp_message_iframe']",
    usercentrics: "#usercentrics-root, #usercentrics-cmp-ui",
    quantcast: ".qc-cmp2-container, #qc-cmp2-container",
    trustarc: "#truste-consent-track, .truste_box_overlay",
    googlefc: ".fc-consent-root",
    youtube: "ytd-consent-bump-v2-lightbox, tp-yt-paper-dialog#dialog.ytd-consent-bump-v2-lightbox",
    google: "form[action*='consent.google'], div[aria-modal='true'][role='dialog'] a[href*='policies.google.com']",
    bbc: "#bbccookies, .bbccookies-banner, section[class*='ConsentBanner']",
    amazon: "#sp-cc",
  };
  r.visible = Object.entries(SEL).filter(([, s]) => [...document.querySelectorAll(s)].some(vis)).map(([k]) => k);
  // any other large fixed overlay that talks about cookies
  const words = /cookie|consent|privacy|your choices|datenschutz|confidentialit/i;
  r.overlay = [...document.querySelectorAll("body *")].filter(e => {
    const s = getComputedStyle(e);
    if (s.position !== "fixed" && s.position !== "sticky") return false;
    if (!vis(e)) return false;
    const b = e.getBoundingClientRect();
    return b.width * b.height > innerWidth * innerHeight * 0.05 && words.test((e.innerText || "").slice(0, 2000));
  }).map(e => (e.id ? "#" + e.id : e.tagName.toLowerCase() + "." + [...e.classList].slice(0, 2).join("."))).slice(0, 3);
  const de = document.documentElement, body = document.body;
  r.scrollLocked = [de, body].filter(Boolean).some(e => {
    const s = getComputedStyle(e);
    return s.overflow === "hidden" || s.overflowY === "hidden" || s.position === "fixed";
  });
  r.pageHeight = Math.round(de.scrollHeight / innerHeight * 10) / 10;   // in screens: a near-empty page is a hint of breakage
  const ck = Object.fromEntries(document.cookie.split("; ").filter(Boolean).map(c => {
    const i = c.indexOf("=");
    return [c.slice(0, i), decodeURIComponent(c.slice(i + 1))];
  }));
  r.consentCookies = Object.keys(ck).filter(n => /consent|optanon|cookiebot|didomi|uc_|euconsent|cmp|gdpr|^SOCS$|^CONSENT$|^_sp_|borlabs|truste|notice_|cookie/i.test(n));
  const rec = {};
  if (window.__tcfapi) {
    rec.tcf = await new Promise(res => {
      const t = setTimeout(() => res("timeout"), 3000);
      try {
        __tcfapi("getTCData", 2, (d, ok) => {
          clearTimeout(t);
          if (!ok || !d) return res("fail");
          const on = o => Object.values(o || {}).filter(Boolean).length;
          res({status: d.eventStatus, cmpId: d.cmpId, string: !!d.tcString,
               purposesOn: on(d.purpose && d.purpose.consents), vendorsOn: on(d.vendor && d.vendor.consents),
               liPurposesOn: on(d.purpose && d.purpose.legitimateInterests)});
        });
      } catch (e) { clearTimeout(t); res("error " + e); }
    });
  }
  if (ck.OptanonConsent) {
    const g = /groups=([^&]*)/.exec(ck.OptanonConsent);
    rec.onetrust = {groups: g ? g[1] : "", closed: "OptanonAlertBoxClosed" in ck};
  }
  if (window.Cookiebot && window.Cookiebot.consent) {
    const c = window.Cookiebot.consent;
    rec.cookiebot = {given: !!window.Cookiebot.hasResponse, preferences: c.preferences, statistics: c.statistics, marketing: c.marketing};
  }
  if (window.Didomi && window.Didomi.getCurrentUserStatus) {
    try {
      const s = window.Didomi.getCurrentUserStatus();
      const p = Object.values(s.purposes || {});
      rec.didomi = {purposesOn: p.filter(x => x.enabled).length, purposes: p.length, choice: !window.Didomi.shouldConsentBeCollected()};
    } catch (e) { rec.didomi = "error " + e; }
  }
  if (window.UC_UI && window.UC_UI.getServicesBaseInfo) {
    try {
      const s = window.UC_UI.getServicesBaseInfo();
      rec.usercentrics = {servicesOn: s.filter(x => x.consent && x.consent.status).length, services: s.length,
                          choice: !window.UC_UI.isConsentRequired()};
    } catch (e) { rec.usercentrics = "error " + e; }
  }
  if (ck.SOCS) rec.google = {SOCS: ck.SOCS.slice(0, 12)};
  if (ck.CONSENT) rec.google = Object.assign(rec.google || {}, {CONSENT: ck.CONSENT.slice(0, 12)});
  r.record = rec;
  return JSON.stringify(r);
})()
