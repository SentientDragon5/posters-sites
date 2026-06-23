#!/usr/bin/env python3
"""
Poster and Web Page Generator
This script parses markdown files in `pages/` that contain `== Poster` and `== Web` sections,
generates dynamic QR codes, compiles clean and responsive web pages and print-ready PDFs,
outputs structured JSON configuration for WordPress migration, and builds a centralized hub.
"""

import os
import re
import glob
import json
import shutil
from datetime import datetime
import urllib.parse
import markdown
import qrcode
from playwright.sync_api import sync_playwright

# Configuration
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(WORKSPACE_ROOT, 'pages')
DOCS_DIR = os.path.join(WORKSPACE_ROOT, 'docs')
ASSETS_DIR = os.path.join(DOCS_DIR, 'assets')
DATA_DIR = os.path.join(DOCS_DIR, 'data')
OUTPUT_DIR = os.path.join(WORKSPACE_ROOT, 'output')

# Base URL for GitHub Pages
BASE_URL = "https://SentientDragon5.github.io/posters-sites"

# HTML Templates
WEB_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <div class="top-bar">
    <div class="top-bar-container">
      <span class="top-bar-left">UC Santa Cruz</span>
    </div>
  </div>
  <header>
    <div class="header-container">
      <a href="index.html" class="logo-wrapper">
        <span class="logo-be-badge">BE</span>
        <span class="logo-text">
          <span class="logo-title">BELS Info Hub</span>
          <span class="logo-subtitle">Baskin Engineering Lab Support</span>
        </span>
      </a>
      <a href="index.html" class="nav-link">Back to Hub</a>
    </div>
  </header>
  <div class="gold-bar"></div>
  <main>
    <article>
      {content_html}
    </article>
  </main>
  <footer>
    <p>&copy; {year} Baskin Engineering Lab Support (BELS)</p>
  </footer>
</body>
</html>
"""

POSTER_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Poster - {title}</title>
  <link rel="stylesheet" href="poster_style.css">
</head>
<body>
  <div class="poster-container">
    <div class="poster-header">
      <div class="poster-logo">
        <span class="be-badge">BE</span> BELS Info Hub
      </div>
      <div class="poster-badge">Scan for Links</div>
    </div>
    <div class="poster-content">
      {content_html}
    </div>
    <div class="poster-footer">
      <div class="footer-text-container">
        <div class="footer-cta">Need more details or links?</div>
        <div class="footer-instruction">Scan the QR code to access the mobile-friendly web page, interactive links, and resources directly.</div>
      </div>
      <div class="qr-code-wrapper">
        <img class="qr-code-img" src="{qr_code_path}" alt="QR Code">
      </div>
    </div>
  </div>
</body>
</html>
"""

HUB_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BELS Info Hub</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <div class="top-bar">
    <div class="top-bar-container">
      <span class="top-bar-left">UC Santa Cruz</span>
    </div>
  </div>
  <header>
    <div class="header-container">
      <a href="index.html" class="logo-wrapper">
        <span class="logo-be-badge">BE</span>
        <span class="logo-text">
          <span class="logo-title">BELS Info Hub</span>
          <span class="logo-subtitle">Baskin Engineering Lab Support</span>
        </span>
      </a>
      <span class="nav-link" style="background-color: transparent; border: none; cursor: default;">Instructional Labs</span>
    </div>
  </header>
  <div class="gold-bar"></div>
  <main>
    <h1 class="hub-title">BELS Info Hub</h1>
    <p class="hub-subtitle">Access digital counterparts and printed PDF posters for instructional lab support, equipment guides, and facilities.</p>
    
    <div class="grid">
      {cards}
    </div>
  </main>
  <footer>
    <p>&copy; {year} Baskin Engineering Lab Support (BELS)</p>
  </footer>
</body>
</html>
"""


def ensure_directories():
    """Create output directories if they don't exist."""
    for path in [DOCS_DIR, ASSETS_DIR, DATA_DIR, OUTPUT_DIR]:
        os.makedirs(path, exist_ok=True)


def parse_markdown_sections(filepath):
    """
    Parse a markdown file into Poster and Web contents.
    Splits strictly by '== Poster' and '== Web' markers.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    poster_lines = []
    web_lines = []
    current_section = None

    for line in lines:
        clean_line = line.strip()
        # Strictly match markers
        if clean_line.startswith("== Poster"):
            current_section = "poster"
            continue
        elif clean_line.startswith("== Web"):
            current_section = "web"
            continue

        if current_section == "poster":
            poster_lines.append(line)
        elif current_section == "web":
            web_lines.append(line)

    return "".join(poster_lines).strip(), "".join(web_lines).strip()


def extract_title(markdown_text, fallback="Untitled Page"):
    """Extract the first h1 heading (# Title) from markdown text."""
    for line in markdown_text.split("\n"):
        if line.strip().startswith("# "):
            return line.strip("# ").strip()
    return fallback


def process_image_references(markdown_content, page_slug):
    """
    Finds markdown image references like ![alt](path), copies the files to
    docs/assets/ directory, and replaces the path with the asset reference.
    """
    # Matches ![alt](path)
    pattern = r'!\[(.*?)\]\((.*?)\)'
    matches = re.findall(pattern, markdown_content)
    
    copied_assets = []
    
    for alt, img_path in matches:
        # Normalize and find source file
        norm_path = img_path.replace('\\', '/')
        
        # Build list of potential source locations
        possible_src_paths = [
            os.path.join(WORKSPACE_ROOT, norm_path),
            os.path.join(PAGES_DIR, norm_path),
            os.path.join(PAGES_DIR, page_slug, os.path.basename(norm_path))
        ]
        
        src_file = None
        for path in possible_src_paths:
            if os.path.exists(path) and os.path.isfile(path):
                src_file = path
                break
                
        if src_file:
            filename = os.path.basename(src_file)
            dest_file = os.path.join(ASSETS_DIR, filename)
            shutil.copy2(src_file, dest_file)
            copied_assets.append(f"assets/{filename}")
            
            # Replace markdown link with docs/ relative path
            markdown_content = markdown_content.replace(img_path, f"assets/{filename}")
            print(f"  Copied asset: {filename}")
        else:
            print(f"  Warning: Asset file '{img_path}' not found.")
            
    return markdown_content, copied_assets


def generate_qr_code(url, filename):
    """Generate a high-quality QR code image."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white")
    dest_path = os.path.join(ASSETS_DIR, filename)
    qr_img.save(dest_path)
    return f"assets/{filename}"


def render_pdf(html_path, pdf_path):
    """Render an HTML page to PDF using Playwright."""
    with sync_playwright() as p:
        # Use the host's existing Google Chrome installation to avoid downloading a separate Chromium binary
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page()
        abs_html_path = os.path.abspath(html_path)
        page.goto(f"file:///{abs_html_path}")
        page.wait_for_load_state("networkidle")
        
        page.pdf(
            path=pdf_path,
            format="Letter",
            print_background=True,
            display_header_footer=False,
            margin={"top": "0in", "right": "0in", "bottom": "0in", "left": "0in"}
        )
        browser.close()


def main():
    print("Starting generator...")
    ensure_directories()

    # Find all .md files in PAGES_DIR
    md_files = glob.glob(os.path.join(PAGES_DIR, "*.md"))
    pages_data = []

    for filepath in md_files:
        filename = os.path.basename(filepath)
        slug = os.path.splitext(filename)[0]
        print(f"\nProcessing page: {slug} ({filename})")

        # Parse sections
        poster_md, web_md = parse_markdown_sections(filepath)
        
        if not poster_md and not web_md:
            print(f"  Skipping: No == Poster or == Web section found in {filename}.")
            continue

        # Extract title
        web_title = extract_title(web_md, fallback=slug.replace('_', ' ').title())
        poster_title = extract_title(poster_md, fallback=web_title)
        
        # Process image assets
        web_md, copied_assets = process_image_references(web_md, slug)
        poster_md, _ = process_image_references(poster_md, slug)

        # Convert Markdown to HTML
        web_html_content = markdown.markdown(web_md, extensions=['extra', 'admonition', 'nl2br'])
        poster_html_content = markdown.markdown(poster_md, extensions=['extra', 'admonition', 'nl2br'])

        # Generate QR Code
        web_page_url = f"{BASE_URL}/{slug}.html"
        qr_filename = f"qr_{slug}.png"
        qr_rel_path = generate_qr_code(web_page_url, qr_filename)
        print(f"  Generated QR code for {web_page_url}")

        # 1. Render and Save Web HTML
        web_html = WEB_TEMPLATE.format(
            title=web_title,
            content_html=web_html_content,
            year=datetime.now().year
        )
        web_dest_path = os.path.join(DOCS_DIR, f"{slug}.html")
        with open(web_dest_path, 'w', encoding='utf-8') as f:
            f.write(web_html)
        print(f"  Saved web page: docs/{slug}.html")

        # 2. Render and Save Poster PDF
        poster_html = POSTER_TEMPLATE.format(
            title=poster_title,
            content_html=poster_html_content,
            qr_code_path=qr_rel_path
        )
        # Save temp HTML file for Playwright rendering
        temp_html_path = os.path.join(DOCS_DIR, f"temp_poster_{slug}.html")
        with open(temp_html_path, 'w', encoding='utf-8') as f:
            f.write(poster_html)
            
        pdf_dest_path = os.path.join(OUTPUT_DIR, f"{slug}.pdf")
        try:
            render_pdf(temp_html_path, pdf_dest_path)
            print(f"  Generated Poster PDF: output/{slug}.pdf")
        except Exception as e:
            print(f"  Error rendering PDF for {slug}: {e}")
        finally:
            if os.path.exists(temp_html_path):
                os.remove(temp_html_path)

        # 3. Output WordPress Import JSON Data
        wp_data = {
            "title": web_title,
            "slug": slug,
            "content_html": web_html_content,
            "meta": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "source_file": f"pages/{filename}",
                "qr_url": web_page_url
            },
            "media": copied_assets
        }
        json_dest_path = os.path.join(DATA_DIR, f"{slug}.json")
        with open(json_dest_path, 'w', encoding='utf-8') as f:
            json.dump(wp_data, f, indent=2)
        print(f"  Saved WordPress migration JSON: docs/data/{slug}.json")

        # Keep info for Hub page
        pages_data.append({
            "title": web_title,
            "slug": slug,
            "pdf_url": f"../output/{slug}.pdf",
            "html_url": f"{slug}.html"
        })

    # 4. Generate Hub / Directory Index Page
    cards_html = []
    for page in pages_data:
        card = f"""
      <div class="card">
        <h2 class="card-title">{page['title']}</h2>
        <p class="card-description">Digital counterpart and printable poster for lab guidelines and support.</p>
        <div class="card-actions">
          <a href="{page['html_url']}" class="btn btn-primary">View Web Page</a>
          <a href="{page['pdf_url']}" class="btn btn-secondary" download>Download PDF</a>
        </div>
      </div>"""
        cards_html.append(card)

    hub_html = HUB_TEMPLATE.format(
      cards="".join(cards_html),
      year=datetime.now().year
    )
    hub_dest_path = os.path.join(DOCS_DIR, "index.html")
    with open(hub_dest_path, 'w', encoding='utf-8') as f:
        f.write(hub_html)
    print("\nRegenerated central Hub directory: docs/index.html")
    print("Done!")


if __name__ == "__main__":
    main()
