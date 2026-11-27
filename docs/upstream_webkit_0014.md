# bugs.webkit.org: new bug

Product: WebKit. Component: Layout and Rendering. Version: WebKit Nightly Build.

Title: Script-driven scrolling relays out every sticky box on each scroll step

setBaseLayoutViewportOrigin() calls setViewportConstrainedObjectsNeedLayout(), which marks every fixed and sticky
renderer needsLayout whenever the layout viewport moves. With scrolling driven from script (window.scrollTo() in
requestAnimationFrame), every step then lays out every sticky box. In WPE WebKit 2.52.6 on a 32-bit ARM TV (LG C1,
Cortex-A55), measured without the Web Inspector attached:

- a long test page with one sticky box: 40 fps;
- a Wikipedia article (Vector 2022, pinned table of contents), JavaScript off: 18 fps.

Sticky offsets are computed from the layer position update after the scroll, so a sticky box does not need a
layout for the scroll itself.

# GitHub PR into WebKit/WebKit (commit message)

Do not relayout sticky boxes on every layout viewport move
https://bugs.webkit.org/show_bug.cgi?id=NNNNNN

Reviewed by NOBODY (OOPS!).

setBaseLayoutViewportOrigin() marked every viewport-constrained renderer needsLayout on each scroll, so
script-driven scrolling laid out every sticky box on every step. Sticky offsets come from the layer position update
after the scroll, so only fixed renderers are marked now. Sticky layers get a compositing geometry update, and a
compositing layer update is scheduled, since without a layout nothing else moves them.

On a 32-bit ARM TV (WPE 2.52.6), rAF-driven scrolling went from 40 to 60.6 fps on a page with one sticky box and
from 18 to 57 fps on a Wikipedia article with JavaScript off.

* Source/WebCore/page/LocalFrameView.cpp:
(WebCore::LocalFrameView::setBaseLayoutViewportOrigin):
