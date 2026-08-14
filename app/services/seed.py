"""Demonstration data — a Tuesday morning rush hour in Accra.

Two things this has to get right, and both are about the demonstration rather than the
code.

**Timestamps are relative to when the seed runs, never fixed.** Confidence decays with a
45-minute half-life, so data seeded with hard-coded times would be fully faded before
anyone looked at it. An examiner would open the map, see nothing, and reasonably conclude
the system does not work. Every report here is placed a number of minutes *before now*.

**It is idempotent.** Identifiers are derived with `uuid5` from a fixed namespace, so
running it twice updates rather than duplicates. A seed script that doubles the data
every time it runs is worse than none.

The locations are real places in Greater Accra. Coordinates are approximate — good to
within a few hundred metres, which is the right precision for a demonstration and is
stated rather than implied.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.geo import to_wkt_point
from app.models import (
    Attachment,
    AttachmentKind,
    Corridor,
    CorridorSubscription,
    Incident,
    IncidentReport,
    IncidentType,
    Notification,
    OutboxMessage,
    Report,
    User,
    UserRole,
)
from app.security import hash_password
from app.services.reports import EVENT_REPORT_SUBMITTED, build_outbox_message

# Fixed namespace so every generated id is stable across runs.
NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

DEMO_PASSWORD = "NkwantaDemo2026"
DEMO_EMAIL_DOMAIN = "nkwanta.demo"


def _id(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:{key}")


# --- accounts -----------------------------------------------------------------


@dataclass(frozen=True)
class SeedUser:
    key: str
    display_name: str
    role: UserRole
    reputation: float


# The four credentialed accounts named in Deployment_and_Source_Links.txt, plus a
# population of commuters whose reputations vary — without that spread, every incident
# would score identically and the reputation weighting would be invisible.
SEED_USERS: list[SeedUser] = [
    SeedUser("commuter", "Ama Owusu", UserRole.COMMUTER, 0.72),
    SeedUser("warden", "Kwesi Boateng", UserRole.WARDEN, 0.80),
    SeedUser("officer", "Insp. Mensah", UserRole.OFFICER, 0.90),
    SeedUser("admin", "System Administrator", UserRole.ADMIN, 0.90),

    SeedUser("kofi", "Kofi Antwi", UserRole.COMMUTER, 0.88),
    SeedUser("adjoa", "Adjoa Mensimah", UserRole.COMMUTER, 0.81),
    SeedUser("yaw", "Yaw Darko", UserRole.COMMUTER, 0.64),
    SeedUser("efua", "Efua Sackey", UserRole.COMMUTER, 0.77),
    SeedUser("kojo", "Kojo Asare", UserRole.COMMUTER, 0.55),
    SeedUser("abena", "Abena Nyarko", UserRole.COMMUTER, 0.69),
    SeedUser("kwabena", "Kwabena Osei", UserRole.COMMUTER, 0.50),
    SeedUser("akosua", "Akosua Frimpong", UserRole.COMMUTER, 0.83),
    SeedUser("fiifi", "Fiifi Quartey", UserRole.COMMUTER, 0.42),
    SeedUser("esi", "Esi Amankwah", UserRole.COMMUTER, 0.75),
    # Two accounts with poor records. Their reports appear on the map but cannot on
    # their own push anything to the police — which is the point of reputation.
    SeedUser("doubtful", "Anon 4471", UserRole.COMMUTER, 0.12),
    SeedUser("unreliable", "Anon 8823", UserRole.COMMUTER, 0.08),
]


# --- places -------------------------------------------------------------------
# Real locations in Greater Accra. Coordinates approximate to a few hundred metres.

PLACES: dict[str, tuple[float, float]] = {
    "Kwame Nkrumah Circle": (5.5709, -0.2074),
    "Achimota junction": (5.6180, -0.2280),
    "Spintex Road": (5.6280, -0.0930),
    "Tetteh Quarshie roundabout": (5.6180, -0.1720),
    "Kaneshie Market": (5.5620, -0.2350),
    "Lapaz": (5.6070, -0.2470),
    "Madina Market": (5.6836, -0.1665),
    "Kasoa toll booth": (5.5340, -0.4160),
    "37 Military Hospital": (5.5850, -0.1870),
    "East Legon": (5.6360, -0.1560),
    "Dansoman": (5.5450, -0.2650),
    "Osu Oxford Street": (5.5570, -0.1820),
    "Nungua": (5.6000, -0.0750),
    "Ashaiman": (5.6900, -0.0330),
    "Weija barrier": (5.5550, -0.3200),
    "Makola, Accra Central": (5.5480, -0.2100),
    "University of Ghana, Legon": (5.6510, -0.1870),
    "Airport Residential": (5.6050, -0.1780),
    "Adabraka": (5.5620, -0.2100),
    "Tema Community 1": (5.6690, -0.0170),
}


@dataclass(frozen=True)
class SeedReport:
    place: str
    incident_type: IncidentType
    reporter_key: str
    minutes_ago: int
    offset_metres: tuple[float, float]   # (north, east) jitter from the place centre
    note: str | None = None


def _offset(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    """Shift a point by a distance in metres. Fine at Accra's latitude."""
    return lat + north_m / 111_320.0, lon + east_m / (111_320.0 * 0.9954)


# The scenario. Eight genuine incidents plus scattered singles, sized so the
# demonstration shows the full range: verified, corroborated, unconfirmed and fading.
SEED_REPORTS: list[SeedReport] = [
    # 1. Major collision at Circle — six reporters, several trusted. Verified.
    SeedReport("Kwame Nkrumah Circle", IncidentType.ACCIDENT, "kofi", 6, (0, 0), "Tipper truck across two lanes"),
    SeedReport("Kwame Nkrumah Circle", IncidentType.ACCIDENT, "adjoa", 7, (40, 30)),
    SeedReport("Kwame Nkrumah Circle", IncidentType.ACCIDENT, "akosua", 9, (-60, 50), "Traffic backed up to Odorna"),
    SeedReport("Kwame Nkrumah Circle", IncidentType.ACCIDENT, "efua", 11, (80, -40)),
    SeedReport("Kwame Nkrumah Circle", IncidentType.ACCIDENT, "yaw", 14, (-30, -70)),
    SeedReport("Kwame Nkrumah Circle", IncidentType.ACCIDENT, "commuter", 17, (55, 65)),

    # 2. Signal outage at Achimota — the power-cut scenario a warden is sent to.
    SeedReport("Achimota junction", IncidentType.SIGNAL_OUTAGE, "esi", 12, (0, 0), "Lights out, no warden on site"),
    SeedReport("Achimota junction", IncidentType.SIGNAL_OUTAGE, "kojo", 15, (50, -40)),
    SeedReport("Achimota junction", IncidentType.SIGNAL_OUTAGE, "abena", 19, (-45, 60)),
    SeedReport("Achimota junction", IncidentType.SIGNAL_OUTAGE, "kwabena", 23, (70, 20)),

    # 3. Flooding on Spintex after rain.
    SeedReport("Spintex Road", IncidentType.FLOOD, "kofi", 22, (0, 0), "Water above kerb height near the lights"),
    SeedReport("Spintex Road", IncidentType.FLOOD, "efua", 26, (-80, 90)),
    SeedReport("Spintex Road", IncidentType.FLOOD, "abena", 31, (60, -70)),

    # 4. Roadworks at Tetteh Quarshie — corroborated, not urgent.
    SeedReport("Tetteh Quarshie roundabout", IncidentType.ROADWORKS, "akosua", 35, (0, 0), "Lane closed for resurfacing"),
    SeedReport("Tetteh Quarshie roundabout", IncidentType.ROADWORKS, "yaw", 41, (55, 45)),

    # 5. Closure at Kaneshie — five reporters. Verified.
    SeedReport("Kaneshie Market", IncidentType.CLOSURE, "adjoa", 18, (0, 0), "Road closed, police diverting"),
    SeedReport("Kaneshie Market", IncidentType.CLOSURE, "kojo", 21, (-50, 40)),
    SeedReport("Kaneshie Market", IncidentType.CLOSURE, "esi", 24, (70, -30)),
    SeedReport("Kaneshie Market", IncidentType.CLOSURE, "kofi", 28, (-40, -60)),
    SeedReport("Kaneshie Market", IncidentType.CLOSURE, "commuter", 33, (35, 75)),

    # 6. Single unconfirmed report from a discredited account. Stays low —
    #    this is the anti-fabrication case.
    SeedReport("Lapaz", IncidentType.CLOSURE, "doubtful", 20, (0, 0), "Road completely blocked"),

    # 7. Older accident at Madina — visibly fading.
    SeedReport("Madina Market", IncidentType.ACCIDENT, "yaw", 95, (0, 0)),
    SeedReport("Madina Market", IncidentType.ACCIDENT, "kwabena", 99, (60, 50)),
    SeedReport("Madina Market", IncidentType.ACCIDENT, "fiifi", 104, (-70, 30)),

    # 8. Flooding at Kasoa.
    SeedReport("Kasoa toll booth", IncidentType.FLOOD, "esi", 44, (0, 0), "Standing water both carriageways"),
    SeedReport("Kasoa toll booth", IncidentType.FLOOD, "abena", 49, (-55, 65)),

    # Scattered single reports — the honest majority of real traffic.
    SeedReport("37 Military Hospital", IncidentType.SURFACE_DEFECT, "kojo", 52, (0, 0), "Large pothole, outbound"),
    SeedReport("East Legon", IncidentType.ROADWORKS, "akosua", 58, (0, 0)),
    SeedReport("Dansoman", IncidentType.SURFACE_DEFECT, "fiifi", 63, (0, 0)),
    SeedReport("Osu Oxford Street", IncidentType.ACCIDENT, "efua", 71, (0, 0), "Minor collision, one lane"),
    SeedReport("Nungua", IncidentType.FLOOD, "unreliable", 38, (0, 0)),
    SeedReport("Ashaiman", IncidentType.SIGNAL_OUTAGE, "kwabena", 67, (0, 0)),
    SeedReport("Weija barrier", IncidentType.CLOSURE, "commuter", 78, (0, 0)),
    SeedReport("Makola, Accra Central", IncidentType.SURFACE_DEFECT, "adjoa", 85, (0, 0)),
    SeedReport("University of Ghana, Legon", IncidentType.ROADWORKS, "esi", 90, (0, 0)),
    SeedReport("Airport Residential", IncidentType.ACCIDENT, "kofi", 47, (0, 0)),
    SeedReport("Adabraka", IncidentType.FLOOD, "abena", 55, (0, 0)),
    SeedReport("Tema Community 1", IncidentType.SURFACE_DEFECT, "yaw", 74, (0, 0)),
]


# --- corridors ----------------------------------------------------------------
# Real Accra roads as coarse polylines — a handful of points each, enough to follow the
# road's shape. Approximate to a few hundred metres, which is the right precision for a
# 250 m match radius and is stated rather than implied.

SEED_CORRIDORS: dict[str, tuple[str, list[tuple[float, float]]]] = {
    "Spintex Road": (
        "Tetteh Quarshie to Baatsona and on towards Tema",
        [(5.6180, -0.1720), (5.6250, -0.1300), (5.6280, -0.0930), (5.6300, -0.0600)],
    ),
    "Ring Road": (
        "Circle through Danquah to Osu",
        [(5.5709, -0.2074), (5.5680, -0.1950), (5.5620, -0.1850), (5.5570, -0.1820)],
    ),
    "N1 Motorway": (
        "Tetteh Quarshie westward past Achimota to Mallam",
        [(5.6180, -0.1720), (5.6180, -0.2280), (5.6070, -0.2470), (5.5750, -0.2900)],
    ),
    "Accra–Kasoa Road": (
        "Mallam through Weija to the Kasoa toll booth",
        [(5.5750, -0.2900), (5.5550, -0.3200), (5.5400, -0.3800), (5.5340, -0.4160)],
    ),
    "Achimota–Circle": (
        "Achimota through Lapaz and Nkrumah interchange",
        [(5.6180, -0.2280), (5.6070, -0.2470), (5.5900, -0.2250), (5.5709, -0.2074)],
    ),
    "Legon–Madina Road": (
        "University of Ghana to Madina market",
        [(5.6510, -0.1870), (5.6650, -0.1750), (5.6836, -0.1665)],
    ),
    "Liberation Road": (
        "37 Military Hospital to Airport and Tetteh Quarshie",
        [(5.5850, -0.1870), (5.6050, -0.1780), (5.6180, -0.1720)],
    ),
    "Winneba Road": (
        "Kaneshie through Odorkor towards Mallam",
        [(5.5620, -0.2350), (5.5700, -0.2600), (5.5750, -0.2900)],
    ),
    "Dansoman Highway": (
        "Kaneshie to Dansoman and the Sakaman junction",
        [(5.5620, -0.2350), (5.5520, -0.2500), (5.5450, -0.2650)],
    ),
    "Tema Motorway": (
        "Tetteh Quarshie to Tema Community 1",
        [(5.6180, -0.1720), (5.6400, -0.1000), (5.6600, -0.0500), (5.6690, -0.0170)],
    ),
    "Ashaiman Road": (
        "Tema Community 1 to Ashaiman",
        [(5.6690, -0.0170), (5.6800, -0.0250), (5.6900, -0.0330)],
    ),
    "Nungua–Teshie Road": (
        "The coastal road from Nungua towards La",
        [(5.6000, -0.0750), (5.5850, -0.1050), (5.5700, -0.1400)],
    ),
    "East Legon–Adjiringanor": (
        "East Legon through Adjiringanor",
        [(5.6360, -0.1560), (5.6450, -0.1400), (5.6500, -0.1250)],
    ),
    "Kwame Nkrumah Avenue": (
        "Accra Central through Adabraka to Circle",
        [(5.5480, -0.2100), (5.5620, -0.2100), (5.5709, -0.2074)],
    ),
    "Graphic Road": (
        "Accra Central to Kaneshie",
        [(5.5480, -0.2100), (5.5550, -0.2250), (5.5620, -0.2350)],
    ),
}

# Which seeded commuters follow which roads, so the demonstration shows real
# notifications rather than an empty list. Chosen to overlap the incident hotspots:
# several people follow Ring Road and Achimota–Circle, where the two verified
# incidents sit.
SEED_SUBSCRIPTIONS: dict[str, list[str]] = {
    "commuter": ["Ring Road", "Achimota–Circle", "Spintex Road"],
    "kofi": ["Ring Road", "N1 Motorway"],
    "adjoa": ["Achimota–Circle", "Graphic Road", "Kwame Nkrumah Avenue"],
    "yaw": ["Spintex Road", "Tema Motorway"],
    "efua": ["Ring Road", "Liberation Road"],
    "kojo": ["Achimota–Circle", "Winneba Road"],
    "abena": ["Legon–Madina Road", "N1 Motorway"],
    "kwabena": ["Dansoman Highway", "Graphic Road"],
    "akosua": ["Ring Road", "Liberation Road", "East Legon–Adjiringanor"],
    "esi": ["Accra–Kasoa Road", "Winneba Road"],
    "fiifi": ["Nungua–Teshie Road"],
    "warden": ["Achimota–Circle"],
    "officer": ["Ring Road"],
}


def _linestring(points: list[tuple[float, float]]) -> str:
    """WKT LINESTRING, longitude first. Same trap as POINT — see app/geo.py."""
    coords = ", ".join(f"{lon} {lat}" for lat, lon in points)
    return f"LINESTRING({coords})"


# --- placeholder evidence -----------------------------------------------------
# Generated rather than embedded, so nothing binary sits in the repository. Both are
# real files of their stated type and both actually open — the point is to exercise
# upload, storage, consent and playback end to end, not to look convincing.
#
# **These are placeholders and the documentation says so.** The photograph is a
# generated gradient, and the recording is a tone rather than speech. Presenting
# synthesised data as if it were real would be the wrong kind of demonstration.


def _placeholder_png(width: int = 320, height: int = 200, seed: int = 0) -> bytes:
    """A small PNG, written by hand. No image library, no committed binary."""
    import struct
    import zlib

    rows = bytearray()
    for y in range(height):
        rows.append(0)                                    # filter byte: none
        for x in range(width):
            rows += bytes((
                (40 + (x * 120 // width) + seed * 17) % 256,
                (70 + (y * 90 // height) + seed * 29) % 256,
                (60 + ((x + y) * 60 // (width + height)) + seed * 11) % 256,
            ))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)   # 8-bit RGB
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + chunk(b"IEND", b""))


def _placeholder_wav(seconds: float = 2.0, hz: int = 320) -> bytes:
    """A short WAV tone. Real audio a browser will play, standing in for speech."""
    import array
    import io
    import math
    import wave

    rate = 8000
    frames = array.array("h")
    for i in range(int(rate * seconds)):
        # Fade both ends so it does not click, which sounds like a bug rather than a tone.
        t = i / rate
        envelope = min(1.0, t * 8, (seconds - t) * 8)
        frames.append(int(9000 * envelope * math.sin(2 * math.pi * hz * t)))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames.tobytes())
    return buffer.getvalue()


@dataclass(frozen=True)
class SeedAttachment:
    """Evidence hung on a seeded report, keyed the same deterministic way."""

    place: str
    reporter_key: str
    minutes_ago: int
    kind: AttachmentKind
    is_public: bool
    duration_seconds: float | None = None


# Chosen to make the demonstration show the full range: a shared recording anyone can
# play, a private one only the control room can hear, and photographs on the two
# verified incidents.
SEED_ATTACHMENTS: list[SeedAttachment] = [
    SeedAttachment("Kwame Nkrumah Circle", "kofi", 6, AttachmentKind.VOICE, True, 14.0),
    SeedAttachment("Kwame Nkrumah Circle", "kofi", 6, AttachmentKind.PHOTO, True),
    SeedAttachment("Kwame Nkrumah Circle", "akosua", 9, AttachmentKind.PHOTO, True),
    SeedAttachment("Achimota junction", "esi", 12, AttachmentKind.VOICE, True, 11.0),
    SeedAttachment("Spintex Road", "kofi", 22, AttachmentKind.PHOTO, True),
    # Not shared: appears for its owner and the control room, and is invisible to other
    # commuters. Worth pointing at in a demonstration.
    SeedAttachment("Kaneshie Market", "adjoa", 18, AttachmentKind.VOICE, False, 9.0),
]


@dataclass(frozen=True)
class SeedResult:
    users_created: int
    reports_created: int
    outbox_queued: int
    corridors_created: int = 0
    subscriptions_created: int = 0
    attachments_created: int = 0


async def clear_demo_data(session: AsyncSession) -> None:
    """Remove the demonstration accounts and everything attached to them.

    **Every report by a demo user, not only the reports this module seeded.**

    The first version deleted reports by their deterministic seed ids and assumed that
    was all a demo account could own. It was wrong the moment anyone used the
    application as `commuter@nkwanta.demo` — those reports have random ids, were not in
    the list, and `reports.reporter_id` is ``ON DELETE RESTRICT``, so deleting the user
    was refused with a foreign key violation.

    The RESTRICT is correct and stays: deleting a user must never silently erase the
    reports that justified sending a warden somewhere (B02). It means a cleanup has to
    remove reports deliberately and in order, which is what this now does.

    Scope is still limited to accounts this module owns, so a database also holding real
    users is untouched.
    """
    user_ids = [_id("user", u.key) for u in SEED_USERS]
    corridor_ids = [_id("corridor", name) for name in SEED_CORRIDORS]

    # Everything these accounts ever filed — seeded or created through the interface.
    report_ids = list(
        await session.scalars(select(Report.id).where(Report.reporter_id.in_(user_ids)))
    )

    if report_ids:
        # Incidents are derived data and rebuildable, so removing one that also contains
        # a non-demo report is safe — the next report to arrive nearby rebuilds it.
        incident_ids = set(
            await session.scalars(
                select(IncidentReport.incident_id).where(IncidentReport.report_id.in_(report_ids))
            )
        )
        if incident_ids:
            # Advisory and clearance rows are keyed on the incident, not the report.
            # Leaving them behind would let a reseed hit a stale idempotency key and
            # silently skip every notification.
            await session.execute(
                delete(OutboxMessage).where(OutboxMessage.aggregate_id.in_(incident_ids))
            )
            await session.execute(delete(Incident).where(Incident.id.in_(incident_ids)))

        await session.execute(
            delete(OutboxMessage).where(OutboxMessage.aggregate_id.in_(report_ids))
        )
        # A contradiction points at the report it contradicts. If one survives while its
        # target is deleted the FK is SET NULL, which is fine — but clearing the link
        # first keeps the delete order honest rather than relying on that.
        await session.execute(
            delete(Report).where(Report.contradicts_id.in_(report_ids))
        )
        # Attachments cascade from reports, so they need no separate delete.
        await session.execute(delete(Report).where(Report.id.in_(report_ids)))

    await session.execute(delete(Notification).where(Notification.user_id.in_(user_ids)))
    await session.execute(
        delete(CorridorSubscription).where(CorridorSubscription.user_id.in_(user_ids))
    )
    await session.execute(delete(Corridor).where(Corridor.id.in_(corridor_ids)))
    await session.execute(delete(User).where(User.id.in_(user_ids)))
    await session.commit()


async def seed(session: AsyncSession, now: dt.datetime | None = None) -> SeedResult:
    """Create the demonstration data. Safe to run repeatedly."""
    now = now or dt.datetime.now(dt.timezone.utc)

    # --- accounts -------------------------------------------------------------
    password_hash = hash_password(DEMO_PASSWORD)
    users_created = 0
    for seed_user in SEED_USERS:
        user_id = _id("user", seed_user.key)
        existing = await session.get(User, user_id)
        if existing is None:
            session.add(
                User(
                    id=user_id,
                    email=f"{seed_user.key}@{DEMO_EMAIL_DOMAIN}",
                    password_hash=password_hash,
                    display_name=seed_user.display_name,
                    role=seed_user.role,
                    reputation=seed_user.reputation,
                )
            )
            users_created += 1
        else:
            existing.reputation = seed_user.reputation
            existing.display_name = seed_user.display_name
            existing.role = seed_user.role
    await session.flush()

    # --- corridors ------------------------------------------------------------
    corridors_created = 0
    for name, (description, points) in SEED_CORRIDORS.items():
        corridor_id = _id("corridor", name)
        if await session.get(Corridor, corridor_id) is None:
            session.add(
                Corridor(
                    id=corridor_id,
                    name=name,
                    description=description,
                    path=_linestring(points),
                )
            )
            corridors_created += 1
    await session.flush()

    # --- who follows what -----------------------------------------------------
    subscriptions_created = 0
    for user_key, corridor_names in SEED_SUBSCRIPTIONS.items():
        for name in corridor_names:
            if name not in SEED_CORRIDORS:
                continue
            existing = await session.get(
                CorridorSubscription, (_id("user", user_key), _id("corridor", name))
            )
            if existing is None:
                session.add(
                    CorridorSubscription(
                        user_id=_id("user", user_key),
                        corridor_id=_id("corridor", name),
                    )
                )
                subscriptions_created += 1
    await session.flush()

    # --- reports and their outbox rows ---------------------------------------
    reports_created = 0
    outbox_queued = 0
    for seed_report in SEED_REPORTS:
        key = f"{seed_report.place}:{seed_report.reporter_key}:{seed_report.minutes_ago}"
        report_id = _id("report", key)
        if await session.get(Report, report_id) is not None:
            continue

        base_lat, base_lon = PLACES[seed_report.place]
        lat, lon = _offset(base_lat, base_lon, *seed_report.offset_metres)

        report = Report(
            id=report_id,
            reporter_id=_id("user", seed_report.reporter_key),
            incident_type=seed_report.incident_type,
            location=to_wkt_point(lat, lon),
            occurred_at=now - dt.timedelta(minutes=seed_report.minutes_ago),
            note=seed_report.note,
            idempotency_key=f"seed:{report_id}",
        )
        session.add(report)
        reports_created += 1

        # Queued exactly as a real submission would, so the worker treats seeded data
        # and live data identically. Nothing about the demonstration is special-cased.
        session.add(build_outbox_message(report, lat, lon))
        outbox_queued += 1

    await session.flush()

    # --- placeholder evidence -------------------------------------------------
    attachments_created = 0
    for i, item in enumerate(SEED_ATTACHMENTS):
        key = f"{item.place}:{item.reporter_key}:{item.minutes_ago}"
        report_id = _id("report", key)
        if await session.get(Report, report_id) is None:
            continue                       # its report was filtered out; skip quietly

        attachment_id = _id("attachment", f"{key}:{item.kind.value}")
        if await session.get(Attachment, attachment_id) is not None:
            continue

        if item.kind is AttachmentKind.VOICE:
            data, content_type = _placeholder_wav(item.duration_seconds or 10.0), "audio/wav"
        else:
            data, content_type = _placeholder_png(seed=i), "image/png"

        session.add(
            Attachment(
                id=attachment_id,
                report_id=report_id,
                kind=item.kind,
                content_type=content_type,
                byte_size=len(data),
                duration_seconds=item.duration_seconds,
                data=data,
                is_public=item.is_public,
            )
        )
        attachments_created += 1

    await session.commit()
    return SeedResult(
        users_created,
        reports_created,
        outbox_queued,
        corridors_created,
        subscriptions_created,
        attachments_created,
    )
