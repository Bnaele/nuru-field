"""Marketplace: what a grower has to sell, and what they need to buy.

This is a prototype and the schema reflects that. A listing is an advert; an
interest is a "can I talk to you about this"; a conversation is the two of them
messaging. There is no order, no cart, no payment and no escrow — money, if any,
changes hands off the app.

Every function here talks to Postgres with the service key, which bypasses Row
Level Security, so the user checks in this module are the ones that actually
protect the data. The policies in schema_marketplace.sql are the second line of
defence for anyone poking at the database with the anon key.
"""

from __future__ import annotations

import logging

from db import get_supabase

log = logging.getLogger(__name__)

KINDS = ("input", "produce")

# PostgREST says PGRST205 (or "relation ... does not exist") when a table the API
# queries was never created. On a fresh database that is a setup step, not a bug,
# so it is reported as one.
NOT_MIGRATED = (
    "The marketplace tables do not exist yet. Run backend/schema_marketplace.sql "
    "in the Supabase SQL editor, then reload."
)


def _is_missing_table(error: Exception) -> bool:
    text = str(error)
    return "PGRST205" in text or "does not exist" in text

# The listing columns the API returns. Kept in one place so browse, detail and
# create cannot drift apart.
LISTING_COLUMNS = (
    "id, seller_id, kind, category, title, description, price_cents, currency, "
    "unit, quantity, region, latitude, longitude, status, created_at"
)


def _table(name: str):
    return get_supabase().table(name)


# --- Profiles ---------------------------------------------------------------


def get_profile(user_id: str) -> dict | None:
    response = _table("profiles").select(
        "user_id, display_name, region, role, contact_note"
    ).eq("user_id", user_id).limit(1).execute()
    return (response.data or [None])[0]


def upsert_profile(
    user_id: str,
    display_name: str,
    region: str | None = None,
    role: str = "both",
    contact_note: str = "",
) -> dict:
    payload = {
        "user_id": user_id,
        "display_name": display_name.strip(),
        "region": (region or "").strip() or None,
        "role": role,
        "contact_note": contact_note.strip(),
    }
    response = _table("profiles").upsert(payload, on_conflict="user_id").execute()
    return (response.data or [payload])[0]


def _names_for(seller_ids: list[str]) -> dict[str, str]:
    """Display names for a page of listings, in one query rather than N."""
    ids = [seller for seller in seller_ids if seller]
    if not ids:
        return {}
    response = _table("profiles").select("user_id, display_name").in_(
        "user_id", list(dict.fromkeys(ids))
    ).execute()
    return {row["user_id"]: row["display_name"] for row in (response.data or [])}


# --- Listings ---------------------------------------------------------------


def create_listing(user_id: str, data: dict) -> dict:
    payload = {
        "seller_id": user_id,
        "kind": data["kind"],
        "category": data.get("category") or "",
        "title": data["title"].strip(),
        "description": (data.get("description") or "").strip(),
        "price_cents": data.get("price_cents"),
        "currency": data.get("currency") or "ZAR",
        "unit": (data.get("unit") or "").strip(),
        "quantity": (data.get("quantity") or "").strip(),
        "region": (data.get("region") or "").strip() or None,
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
    }
    response = _table("listings").insert(payload).execute()
    created = (response.data or [payload])[0]
    created["seller_name"] = (get_profile(user_id) or {}).get("display_name") or "A grower"
    created["images"] = []
    return created


def browse(
    kind: str | None = None,
    category: str | None = None,
    q: str | None = None,
    limit: int = 60,
) -> list[dict]:
    """Active listings, newest first. Public: no account needed to window-shop."""
    query = _table("listings").select(LISTING_COLUMNS).eq("status", "active")
    if kind:
        query = query.eq("kind", kind)
    if category:
        query = query.eq("category", category)
    if q:
        # PostgREST's `or` filter is comma-and-paren delimited, so a search term
        # containing either would rewrite the filter instead of being searched.
        needle = q.strip().replace(",", " ").replace("(", " ").replace(")", " ")
        query = query.or_(f"title.ilike.%{needle}%,description.ilike.%{needle}%")
    try:
        response = query.order("created_at", desc=True).limit(limit).execute()
    except Exception as error:
        if _is_missing_table(error):
            raise LookupError(NOT_MIGRATED) from error
        raise

    rows = response.data or []
    names = _names_for([row["seller_id"] for row in rows])
    images = _images_for([row["id"] for row in rows])
    for row in rows:
        row["seller_name"] = names.get(row["seller_id"], "A grower")
        row["images"] = images.get(row["id"], [])
    return rows


def get_listing(listing_id: str) -> dict | None:
    response = _table("listings").select(LISTING_COLUMNS).eq("id", listing_id).limit(1).execute()
    row = (response.data or [None])[0]
    if row is None:
        return None
    row["seller_name"] = _names_for([row["seller_id"]]).get(row["seller_id"], "A grower")
    row["images"] = _images_for([row["id"]]).get(row["id"], [])
    row["seller_profile"] = get_profile(row["seller_id"])
    return row


def owned_listing(user_id: str, listing_id: str) -> dict | None:
    """The listing, only if this user is the seller. The service key enforces nothing."""
    response = _table("listings").select(LISTING_COLUMNS).eq(
        "id", listing_id
    ).eq("seller_id", user_id).limit(1).execute()
    return (response.data or [None])[0]


def set_status(user_id: str, listing_id: str, status: str) -> dict | None:
    if owned_listing(user_id, listing_id) is None:
        return None
    response = _table("listings").update({"status": status}).eq(
        "id", listing_id
    ).eq("seller_id", user_id).execute()
    return (response.data or [None])[0]


def my_listings(user_id: str) -> list[dict]:
    response = _table("listings").select(LISTING_COLUMNS).eq(
        "seller_id", user_id
    ).order("created_at", desc=True).execute()
    rows = response.data or []
    images = _images_for([row["id"] for row in rows])
    for row in rows:
        row["images"] = images.get(row["id"], [])
    return rows


# --- Images -----------------------------------------------------------------


def _images_for(listing_ids: list[str]) -> dict[str, list[str]]:
    """Signed links, grouped by listing.

    The bucket is private — a listing photo can show someone's yard — so the API
    hands out short-lived links rather than permanent public URLs.
    """
    ids = [listing for listing in listing_ids if listing]
    if not ids:
        return {}

    stored = _table("listing_images").select("listing_id, storage_path").in_(
        "listing_id", ids
    ).order("position").execute()
    paths = [row["storage_path"] for row in (stored.data or [])]
    if not paths:
        return {}

    try:
        signed = get_supabase().storage.from_("listing-photos").create_signed_urls(
            paths, 60 * 60
        )
    except Exception as error:  # storage is a convenience, never a blocker
        log.warning("Could not sign listing images: %s", error)
        return {}

    by_path = {
        item.get("path"): item.get("signedURL") or item.get("signed_url")
        for item in (signed or [])
    }
    grouped: dict[str, list[str]] = {}
    for row in stored.data or []:
        url = by_path.get(row["storage_path"])
        if url:
            grouped.setdefault(row["listing_id"], []).append(url)
    return grouped


def attach_image(
    user_id: str, listing_id: str, filename: str, content_type: str, data: bytes
) -> dict | None:
    """Store one photo for a listing the caller owns."""
    from uuid import uuid4

    if owned_listing(user_id, listing_id) is None:
        return None

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    path = f"{user_id}/{uuid4()}.{suffix}"
    get_supabase().storage.from_("listing-photos").upload(
        path, data, {"content-type": content_type}
    )
    response = _table("listing_images").insert({
        "listing_id": listing_id,
        "storage_path": path,
    }).execute()
    return (response.data or [None])[0]


# --- Interest and conversations ---------------------------------------------


def express_interest(user_id: str, listing_id: str, message: str) -> dict:
    """Open (or reopen) the thread between a buyer and a listing's seller.

    Raises LookupError when the listing does not exist or is not active, and
    ValueError when the seller is asking about their own listing.
    """
    listing = get_listing(listing_id)
    if listing is None or listing["status"] != "active":
        raise LookupError("That listing is no longer available.")
    if listing["seller_id"] == user_id:
        raise ValueError("This is your own listing.")

    interest = _table("interests").upsert(
        {
            "listing_id": listing_id,
            "buyer_id": user_id,
            "message": message.strip(),
        },
        on_conflict="listing_id,buyer_id",
    ).execute()

    conversation = _table("conversations").upsert(
        {
            "listing_id": listing_id,
            "seller_id": listing["seller_id"],
            "buyer_id": user_id,
        },
        on_conflict="listing_id,buyer_id",
    ).execute()

    thread = (conversation.data or [{}])[0]
    if message.strip():
        _table("messages").insert({
            "conversation_id": thread["id"],
            "sender_id": user_id,
            "body": message.strip(),
        }).execute()

    return {
        "conversation_id": thread.get("id"),
        "interest": (interest.data or [{}])[0],
    }


def conversations_for(user_id: str) -> list[dict]:
    """Every thread this user is part of, with the other party's name and the
    listing title, so an inbox can be rendered in one call."""
    response = _table("conversations").select(
        "id, listing_id, seller_id, buyer_id, created_at"
    ).or_(f"seller_id.eq.{user_id},buyer_id.eq.{user_id}").order(
        "created_at", desc=True
    ).execute()
    rows = response.data or []
    if not rows:
        return []

    names = _names_for([row["seller_id"] for row in rows] + [row["buyer_id"] for row in rows])
    titles = {}
    listing_ids = [row["listing_id"] for row in rows]
    listings = _table("listings").select("id, title").in_("id", listing_ids).execute()
    for row in listings.data or []:
        titles[row["id"]] = row["title"]

    for row in rows:
        row["is_seller"] = row["seller_id"] == user_id
        other = row["buyer_id"] if row["is_seller"] else row["seller_id"]
        row["other_name"] = names.get(other, "Someone")
        row["listing_title"] = titles.get(row["listing_id"], "A listing")
    return rows


def thread_for(user_id: str, conversation_id: str) -> dict | None:
    """The conversation and its messages, only for the two participants."""
    response = _table("conversations").select(
        "id, listing_id, seller_id, buyer_id, created_at"
    ).eq("id", conversation_id).limit(1).execute()
    row = (response.data or [None])[0]
    if row is None or user_id not in (row["seller_id"], row["buyer_id"]):
        return None

    messages = _table("messages").select(
        "id, sender_id, body, created_at"
    ).eq("conversation_id", conversation_id).order("created_at").execute()

    row["messages"] = messages.data or []
    return row


def post_message(user_id: str, conversation_id: str, body: str) -> dict | None:
    if thread_for(user_id, conversation_id) is None:
        return None
    response = _table("messages").insert({
        "conversation_id": conversation_id,
        "sender_id": user_id,
        "body": body.strip(),
    }).execute()
    return (response.data or [None])[0]
