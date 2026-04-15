from __future__ import annotations

from io import BytesIO

import fitz

MANUAL_LISTING_URL = "https://manual.example/listings/camden-yard"
MANUAL_BROCHURE_URL = "https://manual.example/assets/camden-yard-brochure.pdf"
MANUAL_MAP_URL = "https://manual.example/assets/camden-yard-map.pdf"

PUBLIC_INDEX_URL = "https://public.example/land"
PUBLIC_LISTING_URL = "https://public.example/listings/camden-yard-opportunity"
PUBLIC_BROCHURE_URL = "https://public.example/assets/camden-yard-brochure.pdf"

SECOND_LISTING_URL = "https://csv.example/listings/peckham-site"

MANUAL_LISTING_HTML = """
<html>
  <head>
    <title>Camden Yard Development Opportunity</title>
    <meta
      name="description"
      content="Cleared London land site with guide price £1,250,000 and auction on 12 June 2026."
    />
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Place",
        "name": "Camden Yard Development Opportunity",
        "description": "Freehold land for sale in London.",
        "address": {
          "streetAddress": "12 Example Rd",
          "addressLocality": "London",
          "postalCode": "NW1 7AA"
        },
        "geo": {
          "latitude": 51.5362,
          "longitude": -0.1421
        }
      }
    </script>
  </head>
  <body>
    <h1>Camden Yard Development Opportunity</h1>
    <p>Guide Price £1,250,000. Auction date 12 June 2026.</p>
    <p>Address: 12 Example Rd, London NW1 7AA.</p>
    <a href="/assets/camden-yard-brochure.pdf">Download brochure PDF</a>
    <a href="/assets/camden-yard-map.pdf">Site map PDF</a>
  </body>
</html>
""".strip()

PUBLIC_INDEX_HTML = """
<html>
  <body>
    <a class="listing-link" href="/listings/camden-yard-opportunity">Camden Yard</a>
  </body>
</html>
""".strip()

PUBLIC_LISTING_HTML = """
<html>
  <head>
    <title>Camden Yard Land Site | Public Page</title>
    <meta name="description" content="Land site in Camden with guide price £1,240,000." />
  </head>
  <body>
    <h1>Camden Yard Land Site</h1>
    <p>Development opportunity at 12 Example Road, London NW1 7AA.</p>
    <p>Guide Price £1,240,000.</p>
    <p>Coordinates 51.5362,-0.1421.</p>
    <a href="/assets/camden-yard-brochure.pdf">Brochure</a>
  </body>
</html>
""".strip()

CSV_IMPORT_TEXT = (
    "source_listing_id,headline,description,address,price,brochure_url,"
    "canonical_url,listing_type,status\n"
    'csv-1,Peckham Corner Site,Cleared site in South London,'
    '44 Rye Lane London SE15 5BS,"£875,000",,'
    "https://csv.example/listings/peckham-site,LAND,LIVE"
)


def build_pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    buffer = BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


MANUAL_BROCHURE_PDF = build_pdf_bytes("Camden Yard brochure text.")
MANUAL_MAP_PDF = build_pdf_bytes("Camden Yard map sheet.")
PUBLIC_BROCHURE_PDF = MANUAL_BROCHURE_PDF
