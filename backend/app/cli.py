"""
AgriTech CLI — developer tool for managing tenants, features, and config.

Usage (from the backend/ folder):

    py.bat -m app.cli features list <tenant_id>
    py.bat -m app.cli features enable <tenant_id> --features agent,chat
    py.bat -m app.cli features disable <tenant_id> --features diagnosis,finance
    py.bat -m app.cli features set-config <tenant_id> finance '{"exclude_cost_categories":["water"]}'
    py.bat -m app.cli tenants list

This is a developer tool, not a customer-facing interface. It runs
against whatever DATABASE_URL is configured in .env. Run it on your
dev machine only; production changes go through Phase 10's admin UI.
"""
import argparse
import json
import sys
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.models.tenant import Tenant
from app.services import features_service as fs


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        print(f"Error: '{value}' is not a valid UUID.", file=sys.stderr)
        sys.exit(1)


def _split_features(value: str) -> list[str]:
    """Parse 'a,b,c' into ['a', 'b', 'c'], stripping whitespace."""
    return [f.strip() for f in value.split(",") if f.strip()]


def _print_table(rows: list[tuple[str, str]]) -> None:
    if not rows:
        return
    width = max(len(r[0]) for r in rows)
    for key, val in rows:
        print(f"  {key.ljust(width)}   {val}")


# --- features commands -------------------------------------------------------

def cmd_features_list(args) -> None:
    tenant_id = _parse_uuid(args.tenant_id)
    db = SessionLocal()
    try:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            print(f"Tenant {tenant_id} not found.", file=sys.stderr)
            sys.exit(1)

        name = getattr(tenant, "name", None) or "(unnamed)"
        print(f"\nTenant: {name}  [{tenant_id}]\n")

        features = fs.list_features(db, tenant_id)
        rows = []
        for key, info in features.items():
            state = "ON " if info["enabled"] else "OFF"
            default_note = ""
            if info["default"] is not None and info["enabled"] != info["default"]:
                default_note = f"  (default: {'ON' if info['default'] else 'OFF'})"
            config_note = ""
            if info["config"]:
                config_note = f"  config={json.dumps(info['config'])}"
            rows.append((key, f"{state}  {info['description']}{default_note}{config_note}"))
        _print_table(rows)
        print()
    finally:
        db.close()


def cmd_features_enable(args) -> None:
    tenant_id = _parse_uuid(args.tenant_id)
    keys = _split_features(args.features)
    if not keys:
        print("No features specified. Use --features a,b,c", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        for key in keys:
            fs.enable_feature(db, tenant_id, key)
            print(f"  ✓ enabled  {key}")
    finally:
        db.close()


def cmd_features_disable(args) -> None:
    tenant_id = _parse_uuid(args.tenant_id)
    keys = _split_features(args.features)
    if not keys:
        print("No features specified. Use --features a,b,c", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        for key in keys:
            fs.disable_feature(db, tenant_id, key)
            print(f"  ✗ disabled {key}")
    finally:
        db.close()


def cmd_features_set_config(args) -> None:
    tenant_id = _parse_uuid(args.tenant_id)
    try:
        config = json.loads(args.config_json)
    except json.JSONDecodeError as e:
        print(f"Error: config must be valid JSON ({e})", file=sys.stderr)
        sys.exit(1)
    if not isinstance(config, dict):
        print("Error: config must be a JSON object, e.g. '{\"key\":\"value\"}'", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        fs.set_config(db, tenant_id, args.feature_key, config)
        print(f"  ✓ config set for {args.feature_key}: {json.dumps(config)}")
    finally:
        db.close()


# --- tenants commands --------------------------------------------------------

def cmd_tenants_list(args) -> None:
    db = SessionLocal()
    try:
        tenants = db.execute(select(Tenant).order_by(Tenant.id)).scalars().all()
        if not tenants:
            print("No tenants found.")
            return
        rows = []
        for t in tenants:
            name = getattr(t, "name", None) or "(unnamed)"
            rows.append((str(t.id), name))
        _print_table(rows)
    finally:
        db.close()


# --- parser ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="app.cli",
        description="AgriTech developer CLI",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # features
    features = sub.add_parser("features", help="Manage per-tenant feature flags")
    fsub = features.add_subparsers(dest="subcommand", required=True)

    p_list = fsub.add_parser("list", help="List all features for a tenant")
    p_list.add_argument("tenant_id")
    p_list.set_defaults(func=cmd_features_list)

    p_enable = fsub.add_parser("enable", help="Enable one or more features")
    p_enable.add_argument("tenant_id")
    p_enable.add_argument("--features", required=True, help="Comma-separated feature keys")
    p_enable.set_defaults(func=cmd_features_enable)

    p_disable = fsub.add_parser("disable", help="Disable one or more features")
    p_disable.add_argument("tenant_id")
    p_disable.add_argument("--features", required=True, help="Comma-separated feature keys")
    p_disable.set_defaults(func=cmd_features_disable)

    p_config = fsub.add_parser("set-config", help="Set JSON config for a feature")
    p_config.add_argument("tenant_id")
    p_config.add_argument("feature_key")
    p_config.add_argument("config_json", help='JSON object, e.g. \'{"k":"v"}\'')
    p_config.set_defaults(func=cmd_features_set_config)

    # tenants
    tenants = sub.add_parser("tenants", help="Manage tenants")
    tsub = tenants.add_subparsers(dest="subcommand", required=True)

    p_tlist = tsub.add_parser("list", help="List all tenants")
    p_tlist.set_defaults(func=cmd_tenants_list)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()