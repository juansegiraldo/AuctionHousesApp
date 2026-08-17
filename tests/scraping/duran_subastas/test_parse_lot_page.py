from pathlib import Path

from scraping.houses.duran_subastas.parsers import parse_lot_page


def test_parse_lot_page_extracts_detail():
    html = Path(__file__).parent / "fixtures" / "lot_page_pintura.html"
    detail = parse_lot_page(html.read_text(encoding="utf-8"))
    assert detail["category"] == "pintura"
    assert detail["lot_title"] == "Lote 100 - Pintura al óleo"
    assert detail["price_estimate_min"] == 1500
    assert detail["price_estimate_max"] == 2500
    assert detail["image_url"] == "https://www.duran-subastas.com/img/lote100.jpg"


def test_parse_lot_page_extracts_category_from_badge():
    html = """
    <html>
      <head>
        <meta property="og:title" content="Joan Miro" />
      </head>
      <body>
        <div class="cat">Categorias</div>
        <span class="badge"><img src="/cat-614.png">OBRA GRÁFICA</span>
      </body>
    </html>
    """
    detail = parse_lot_page(html)
    assert detail["category"] == "obra_grafica"


def test_parse_lot_page_extracts_reference_breadcrumb_and_artist_years():
    html = """
    <html>
      <body>
        <div class="referencia-ficha"><span>Lote: 322</span></div>
        <div class="ficha-info-title w-100">
          <div class="titleficha w-100 secondary-color-text">Manuel Viola. Les Coqs du Marché commun</div>
        </div>
        <li itemprop="itemListElement" itemscope itemtype="https://schema.org/ListItem">
          <a itemprop="item" href="https://www.duran-subastas.com/es/subasta/subasta-652-enero-2026_652-001">
            <span itemprop="name">Subasta 652 Enero 2026</span>
          </a>
        </li>
        <div class="col-xs-4 pb-2">Autor</div>
        <div class="col-xs-8 pb-2"><strong>VIOLA, MANUEL (1919 - 1987)</strong></div>
        <div class="col-xs-4 pb-2">Título</div>
        <div class="col-xs-8 pb-2"><strong>Les Coqs du Marché commun</strong></div>
        <div class="pre">
          <p class="pre-title-principal adj-text">VENDIDO POR</p>
          <p class="pre-price">1.200 €</p>
        </div>
        <div class="pre">
          <p class="pre-title-principal">Precio salida</p>
          <p class="pre-price">500 €</p>
        </div>
      </body>
    </html>
    """
    detail = parse_lot_page(html)
    assert detail["lot_number"] == 322
    assert detail["lot_title"] == "Les Coqs du Marché commun"
    assert detail["auction_start_date"] == "Enero 2026"
    assert detail["artist_birth_year"] == 1919
    assert detail["artist_death_year"] == 1987
    assert detail["price_estimate_min"] == 500
    assert detail["price_sold"] == 1200


def test_parse_lot_page_prefers_detail_author_over_title_guess():
    html = Path(__file__).parent / "fixtures" / "lot_page_botero_504_154.html"
    detail = parse_lot_page(html.read_text(encoding="utf-8"))

    assert detail["lot_number"] == 154
    assert detail["artist_raw"] == "BOTERO, FERNANDO (1932 - 2023)"
    assert detail["artist_name"] == "BOTERO, FERNANDO"
    assert detail["artist_name"] != '"Madre Superiora"'
