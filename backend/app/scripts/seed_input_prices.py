"""
Seed the input_prices table with global catalog prices.

    ⚠️  These are PLACEHOLDER values for development. Before production:
        - Verify against HARTI publications
        - Replace with current, region-appropriate prices
        - Update the `source` field to cite the actual source

Usage:
    ./py.bat -m app.scripts.seed_input_prices
    ./py.bat -m app.scripts.seed_input_prices --reset   (delete existing global rows first)
"""
import argparse
import sys
from datetime import date

from app.db.models.input_price import InputCategory, InputPrice
from app.db.session import SessionLocal


# --- Seed data --------------------------------------------------------------
#
# Tuple format: (category, product_name, active_ingredient, unit, price_lkr, source)
#
# All prices in LKR, all sourced as 'seed_placeholder' until verified.

SEED_PRICES = [
    # ---- Fertilizers (per kg) ----
    (InputCategory.FERTILIZER, "Urea 46% N",                 "urea",             "kg", 340.00),
    (InputCategory.FERTILIZER, "Triple Superphosphate (TSP)", "tsp",              "kg", 380.00),
    (InputCategory.FERTILIZER, "Muriate of Potash (MOP)",    "mop",              "kg", 320.00),
    (InputCategory.FERTILIZER, "NPK 15-15-15",               "npk_15_15_15",     "kg", 420.00),
    (InputCategory.FERTILIZER, "Dolomite lime",              "dolomite",         "kg",  45.00),
    (InputCategory.FERTILIZER, "Compost (mature)",           "compost",          "kg",  30.00),

    # ---- Fungicides ----
    (InputCategory.FUNGICIDE, "Copper oxychloride 50% WP",   "copper_oxychloride", "kg", 2800.00),
    (InputCategory.FUNGICIDE, "Mancozeb 80% WP",             "mancozeb",           "kg", 2200.00),
    (InputCategory.FUNGICIDE, "Carbendazim 50% WP",          "carbendazim",        "kg", 2500.00),
    (InputCategory.FUNGICIDE, "Bordeaux mixture (prepared)", "bordeaux_mixture",   "L",   150.00),

    # ---- Insecticides ----
    (InputCategory.INSECTICIDE, "Imidacloprid 200 SL",       "imidacloprid",     "L",  8500.00),
    (InputCategory.INSECTICIDE, "Thiamethoxam 25% WG",       "thiamethoxam",     "kg", 12000.00),
    (InputCategory.INSECTICIDE, "Abamectin 1.8% EC",         "abamectin",        "L",  6500.00),
    (InputCategory.INSECTICIDE, "Neem oil (cold pressed)",   "neem_oil",         "L",  1800.00),

    # ---- Water ----
    (InputCategory.WATER, "Irrigation water (agricultural)",  "water",            "L",     1.20),

    # ---- Labor ----
    (InputCategory.LABOR, "Farm labor (general)",             "farm_labor_general", "hr", 350.00),
    (InputCategory.LABOR, "Skilled labor (operator)",         "farm_labor_skilled", "hr", 550.00),

    # ---- Energy ----
    (InputCategory.ENERGY, "Electricity (CEB industrial)",   "ceb_industrial",   "kWh",   32.00),

    # ---- Fuel ----
    (InputCategory.FUEL, "Diesel (auto)",                    "diesel",           "L",    335.00),
    (InputCategory.FUEL, "Petrol (octane 92)",               "petrol_92",        "L",    366.00),
]


# --- Seed logic -------------------------------------------------------------

def seed(reset: bool) -> int:
    db = SessionLocal()
    today = date.today()
    try:
        if reset:
            n = (
                db.query(InputPrice)
                .filter(InputPrice.tenant_id.is_(None))
                .delete(synchronize_session=False)
            )
            db.commit()
            print(f"Deleted {n} existing global price rows")

        inserted = 0
        skipped = 0
        for category, name, ingredient, unit, price in SEED_PRICES:
            existing = (
                db.query(InputPrice)
                .filter(
                    InputPrice.tenant_id.is_(None),
                    InputPrice.product_name == name,
                    InputPrice.valid_until.is_(None),
                )
                .first()
            )
            if existing is not None:
                skipped += 1
                continue

            db.add(InputPrice(
                tenant_id=None,
                category=category,
                product_name=name,
                active_ingredient=ingredient,
                unit=unit,
                price_lkr=price,
                region="LK",
                valid_from=today,
                source="seed_placeholder",
                verified=False,
                notes="Placeholder value; verify against HARTI before production use.",
            ))
            inserted += 1

        db.commit()
        print(f"Inserted {inserted} new price rows, skipped {skipped} existing")
        return 0
    finally:
        db.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Seed input prices.")
    p.add_argument(
        "--reset", action="store_true",
        help="Delete existing global prices before seeding",
    )
    args = p.parse_args()
    return seed(reset=args.reset)


if __name__ == "__main__":
    sys.exit(main())