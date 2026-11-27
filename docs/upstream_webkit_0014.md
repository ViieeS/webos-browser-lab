# bugs.webkit.org: existing bug 165460

No new bug needed: https://bugs.webkit.org/show_bug.cgi?id=165460 ("Visual viewports trigger layout on scrolling,
and should not need to", Layout and Rendering, filed 2016-12-06 by Simon Fraser, NEW, unassigned, no comments) says
setBaseLayoutViewportOrigin() calls setViewportConstrainedObjectsNeedLayout() although it should not be necessary.
The text below can go into that bug as a comment with the measurements.

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
https://bugs.webkit.org/show_bug.cgi?id=165460

Reviewed by NOBODY (OOPS!).

setBaseLayoutViewportOrigin() marked every viewport-constrained renderer needsLayout on each scroll, so
script-driven scrolling laid out every sticky box on every step. Sticky offsets come from the layer position update
after the scroll, so only fixed renderers are marked now. Sticky layers get a compositing geometry update, and a
compositing layer update is scheduled, since without a layout nothing else moves them.

On a 32-bit ARM TV (WPE 2.52.6), rAF-driven scrolling went from 40 to 60.6 fps on a page with one sticky box and
from 18 to 57 fps on a Wikipedia article with JavaScript off.

* Source/WebCore/page/LocalFrameView.cpp:
(WebCore::LocalFrameView::setBaseLayoutViewportOrigin):

# Status (2026-11-27)

Submitted as https://github.com/WebKit/WebKit/pull/82406 (commit 0722f698f4 on main 8457cc5090). The text above is
the first draft. The PR version differs: on main it recomputes layer positions from the new origin instead of only
scheduling a compositing update, because the scroll path updates layer positions before the origin moves.
