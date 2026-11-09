"""Render poster/poster.html to an A1 PDF and a low-resolution preview PNG.

Chromium via Playwright. The PDF keeps the SVG figures as vector, so the only
raster content is the three maps, which carry a shaded-relief basemap anyway
and are supplied at 600 dpi.

Run: python scripts/11_render_poster.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTER = ROOT / "poster"
HTML = POSTER / "poster.html"
PDF = POSTER / "poster.pdf"
PREVIEW = POSTER / "poster_preview.png"

# A1 portrait.
WIDTH_MM, HEIGHT_MM = 594, 841
CSS_PX_PER_MM = 96 / 25.4           # CSS reference pixel
PREVIEW_SCALE = 1.0                 # preview only; the PDF is the print master


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed: pip install playwright "
                 "&& python -m playwright install chromium")

    if not HTML.exists():
        sys.exit("missing {}".format(HTML))

    url = HTML.resolve().as_uri()
    width_px = round(WIDTH_MM * CSS_PX_PER_MM)
    height_px = round(HEIGHT_MM * CSS_PX_PER_MM)
    print("rendering {}\n  A1 portrait {} x {} mm  ({} x {} css px)".format(
        HTML.name, WIDTH_MM, HEIGHT_MM, width_px, height_px))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width_px, "height": height_px})
        # "networkidle" is unreliable for a local file with several large
        # images; wait for decode completion explicitly instead.
        page.goto(url, wait_until="load", timeout=120_000)
        page.wait_for_function(
            "() => Array.from(document.images).every(i => i.complete)",
            timeout=120_000)
        page.emulate_media(media="print")

        # Fail loudly rather than shipping a poster with missing figures.
        missing = page.evaluate(
            "() => Array.from(document.images)"
            ".filter(i => !i.complete || i.naturalWidth === 0)"
            ".map(i => i.getAttribute('src'))")
        if missing:
            sys.exit("images failed to load:\n  " + "\n  ".join(missing))
        print("  {} images loaded".format(len(page.query_selector_all("img"))))

        # Print-resolution check. A raster placed larger than the size it was
        # saved at drops below 300 dpi, which a preview will not reveal. The
        # hero map sits close to the limit, so enlarging it would fail here.
        placed = page.evaluate(
            "() => Array.from(document.images).map(i => ({"
            " src: i.getAttribute('src').split('/').pop(),"
            " natW: i.naturalWidth, wpx: i.getBoundingClientRect().width }))")
        low = []
        for img in placed:
            if img["src"].endswith(".svg"):
                continue
            width_mm = img["wpx"] / CSS_PX_PER_MM
            dpi = img["natW"] / (width_mm / 25.4)
            print("  {:<34} {:6.1f} mm  {:4.0f} dpi{}".format(
                img["src"], width_mm, dpi, "" if dpi >= 300 else "   TOO LOW"))
            if dpi < 300:
                low.append((img["src"], round(dpi)))
        if low:
            sys.exit("below 300 dpi at the placed size: {}".format(low))

        # Overflow check: the .page box is a fixed A1 sheet, so anything taller
        # than it is silently clipped in the PDF.
        overflow = page.evaluate(
            "() => { const el = document.querySelector('.page');"
            " return {scroll: el.scrollHeight, client: el.clientHeight,"
            "  body: document.body.scrollHeight}; }")
        print("  content {} px in a {} px sheet".format(
            overflow["scroll"], overflow["client"]))
        if overflow["scroll"] > overflow["client"] + 2:
            over_mm = (overflow["scroll"] - overflow["client"]) / CSS_PX_PER_MM
            print("  WARNING: content overflows the sheet by "
                  "{:.1f} mm and will be clipped".format(over_mm))

        page.pdf(path=str(PDF), width="{}mm".format(WIDTH_MM),
                 height="{}mm".format(HEIGHT_MM), print_background=True,
                 prefer_css_page_size=True, margin={
                     "top": "0", "right": "0", "bottom": "0", "left": "0"})
        print("  wrote {} ({:.1f} MB)".format(PDF.name, PDF.stat().st_size / 1e6))

        browser.close()

        # Preview. LCD subpixel antialiasing tints small dark text at reduced
        # scales, which made black body copy look orange in review; disable it
        # so the preview represents the PDF honestly.
        browser = p.chromium.launch(args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": width_px, "height": height_px},
            device_scale_factor=PREVIEW_SCALE)
        page = context.new_page()
        page.goto(url, wait_until="load", timeout=120_000)
        page.wait_for_function(
            "() => Array.from(document.images).every(i => i.complete)",
            timeout=120_000)
        page.screenshot(path=str(PREVIEW), full_page=False)
        print("  wrote {} ({:.1f} MB, scale {})".format(
            PREVIEW.name, PREVIEW.stat().st_size / 1e6, PREVIEW_SCALE))
        browser.close()

    print("\nPDF page size should read 594 x 841 mm in a viewer.")


if __name__ == "__main__":
    main()
