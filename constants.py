from pathlib import Path
from urllib.parse import urlencode

base_url = "https://web.stockedge.com/sector/"

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

sectors = [
    "abrasives/1",
    "alcohol/3",
    "media-entertainment/26",
    "logistics/25",
    "telecom/39",
    "textile/40",
    "ratings/35",
    "information-technology/24",
    "mining/27",
    "photographic-product/32",
    "aviation/5",
    "fast-moving-consumer-goods/17",
    "healthcare/19",
    "gas-transmission/18",
    "diamond-jewellery/12",
    "automobile-ancillaries/4",
    "agriculture/2",
    "retailing/37",
    "diversified/13",
    "chemicals/8",
    "trading/41",
    "hospitality/20",
    "industrials-gases-fuels/21",
    "consumer-durables/10",
    "paper/31",
    "plastic-products/33",
    "banking/6",
    "other/30",
    "finance/16",
    "miscellaneous/28",
    "power/34",
    "electricals/14",
    "infrastructure/22",
    "construction-materials/9",
    "capital-goods/7",
    "realty/36",
    "ship-building/38",
    "iron-steel/23",
    "crude-oil/11",
    "non-ferrous-metals/29",
    "ferro-manganese/15",
]

section = [
    "sector-gainers",
    "sector-losers"
]

time_period = [
    "1D",
    "1W",
    "1M",
    "3M",
    "6M",
    "1Y",
    "3Y",
    "5Y",
]


def build_sector_url(
    sector: str,
    section: str,
    period: str,
) -> str:
    """Build a StockEdge sector page URL.

    Args:
        sector: one entry from ``sectors``, e.g. ``"finance/16"``.
        section: one entry from ``section``, e.g. ``"sector-gainers"``.
        period: one entry from ``time_period``, e.g. ``"1M"``.

    Example::

        build_sector_url("finance/16", "sector-gainers", "1M")
        # -> https://web.stockedge.com/sector/finance/16?section=sector-gainers&time-period=1M
    """
    path = f"{base_url.rstrip('/')}/{sector.lstrip('/')}"
    q = urlencode({"section": section, "time-period": period})
    return f"{path}?{q}"