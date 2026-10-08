from datetime import datetime, timedelta
import pandas as pd
from playwright.sync_api import sync_playwright

from power.utils.upload import save_state_5min_load_from_csv


SLDC_URL = "https://www.delhisldc.org/Loaddata.aspx?mode="


def ingest_sldc_daily_data():
    """
    Fetch SLDC daily load data (T-1) via browser
    and insert into StateLoad5Min using existing logic.
    """
    #target_date = datetime.today() - timedelta(days=1)
    target_date = datetime(2026, 1, 20)
    date_str = target_date.strftime("%d/%m/%Y")

    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # real browser
        page = browser.new_page()
        page.goto(SLDC_URL + date_str, timeout=60000)
        page.wait_for_timeout(5000)

        rows = page.evaluate("""
            () => {
                const out = [];
                document.querySelectorAll("table tr").forEach(tr => {
                    const td = tr.querySelectorAll("td");
                    if (td.length >= 7) {
                        const time = td[0].innerText.trim();
                        if (/^\\d{2}:\\d{2}$/.test(time)) {
                            out.push({
                                DateTime: time,
                                Delhi: td[1].innerText.trim(),
                                BRPL: td[2].innerText.trim(),
                                BYPL: td[3].innerText.trim(),
                                NDPL: td[4].innerText.trim(),
                                NDMC: td[5].innerText.trim(),
                                MES: td[6].innerText.trim(),
                            });
                        }
                    }
                });
                return out;
            }
        """)

        browser.close()

    if not rows:
        print("[SLDC] No data available")
        return 0

    df = pd.DataFrame(rows)
    df["DateTime"] = df["DateTime"].apply(
        lambda t: f"{date_str} {t}"
    )

    count = save_state_5min_load_from_csv(df)
    print(f"[SLDC] Inserted / Updated {count} rows")

    return count
