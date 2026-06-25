import pandas as pd

from src.data.okx_announcements import normalize_announcement
from src.data.okx_listing_events import build_listing_events, infer_symbol_from_title


def test_normalize_announcement_accepts_variant_keys():
    item = normalize_announcement(
        {
            "annId": 123,
            "annTitle": "OKX to list DOGE perpetual futures",
            "publishTime": "2026-06-25T08:00:00Z",
            "listTime": "2026-06-25T09:00:00Z",
            "detailUrl": "https://www.okx.com/help/doge",
        }
    )

    assert item.announcement_id == "123"
    assert item.title.startswith("OKX to list DOGE")
    assert item.listing_time == "2026-06-25T09:00:00Z"


def test_infer_symbol_from_title_skips_generic_tokens():
    assert infer_symbol_from_title("OKX will list DOGE perpetual futures") == "DOGE"


def test_build_listing_events_deduplicates_inst_id_and_time():
    announcements = [
        normalize_announcement(
            {
                "id": "1",
                "title": "OKX will list DOGE perpetual futures",
                "publishedAt": "2026-06-25T08:00:00Z",
                "listingTime": "2026-06-25T09:00:00Z",
            }
        ),
        normalize_announcement(
            {
                "id": "2",
                "title": "OKX will list DOGE perpetual futures soon",
                "publishedAt": "2026-06-25T08:05:00Z",
                "listingTime": "2026-06-25T09:00:00Z",
            }
        ),
    ]
    instruments = pd.DataFrame([{"baseCcy": "DOGE", "instId": "DOGE-USDT-SWAP"}])

    frame = build_listing_events(announcements, instruments)

    assert len(frame) == 1
    assert frame.iloc[0]["inst_id"] == "DOGE-USDT-SWAP"
