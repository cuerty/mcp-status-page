from datetime import UTC, datetime, timedelta

from mcp_status_page.models import Component, Incident, Level, Service, ServiceStatus, parse_dt, worst

SVC = Service(key="demo", provider="statuspage", url="https://status.example.com", name="Demo")
NOW = datetime(2026, 11, 25, 12, tzinfo=UTC)


def make(**kwargs) -> ServiceStatus:
    return ServiceStatus.for_service(SVC, now=NOW, **kwargs)


def test_worst_orders_by_severity():
    assert worst([Level.DEGRADED, Level.MAJOR_OUTAGE, Level.MAINTENANCE]) is Level.MAJOR_OUTAGE
    assert worst([]) is Level.OPERATIONAL


def test_empty_status_is_operational():
    s = make()
    assert s.level is Level.OPERATIONAL
    assert s.summary == "All systems operational"
    assert (s.service, s.name, s.provider, s.page_url) == ("demo", "Demo", "statuspage", "https://status.example.com")


def test_error_means_unknown_never_operational():
    s = make(error="timeout")
    assert s.level is Level.UNKNOWN
    assert s.summary == "Status unknown: timeout"


def test_components_deduped_sorted_operational_dropped():
    s = make(
        components=[
            Component(name="API", level=Level.DEGRADED),
            Component(name="Web", level=Level.OPERATIONAL),
            Component(name="Git", level=Level.MAJOR_OUTAGE),
            Component(name="API", level=Level.PARTIAL_OUTAGE),
        ]
    )
    assert [(c.name, c.level) for c in s.components] == [
        ("Git", Level.MAJOR_OUTAGE),
        ("API", Level.PARTIAL_OUTAGE),
    ]
    assert s.level is Level.MAJOR_OUTAGE
    assert s.summary == "Major outage: Git, API"


def test_summary_counts_incidents_and_extra_components():
    comps = [Component(name=f"c{i}", level=Level.DEGRADED) for i in range(7)]
    s = make(components=comps, incidents=[Incident(title="Boom", level=Level.DEGRADED)])
    assert s.summary == "Degraded: c0, c1, c2, c3, c4 +2 more (1 incident)"


def test_summary_uses_incident_titles_without_components():
    s = make(incidents=[Incident(title="Login errors", level=Level.PARTIAL_OUTAGE)])
    assert s.summary == "Partial outage: Login errors (1 incident)"


def test_maintenance_window_keeps_in_progress_and_next_24h():
    in_progress = Incident(title="DB upgrade", level=Level.MAINTENANCE)
    soon = Incident(title="Soon", level=Level.OPERATIONAL, started_at=NOW + timedelta(hours=3))
    later = Incident(title="Later", level=Level.OPERATIONAL, started_at=NOW + timedelta(days=3))
    s = make(maintenance=[in_progress, soon, later])
    assert [m.title for m in s.maintenance] == ["DB upgrade", "Soon"]
    assert s.level is Level.MAINTENANCE


def test_scheduled_maintenance_does_not_raise_level():
    soon = Incident(title="Soon", level=Level.OPERATIONAL, started_at=NOW + timedelta(hours=3))
    s = make(maintenance=[soon])
    assert s.level is Level.OPERATIONAL
    assert s.summary == "All systems operational; upcoming maintenance: Soon"


def test_filtered_recomputes_level():
    s = make(
        components=[
            Component(name="S3", level=Level.MAJOR_OUTAGE, group="us-east-1"),
            Component(name="EC2", level=Level.DEGRADED, group="eu-west-1"),
        ],
        incidents=[Incident(title="S3 errors", level=Level.MAJOR_OUTAGE, components=["S3"])],
    )
    eu = s.filtered("EU-WEST")
    assert [c.name for c in eu.components] == ["EC2"]
    assert eu.incidents == []
    assert eu.level is Level.DEGRADED
    assert s.filtered("s3").level is Level.MAJOR_OUTAGE
    assert s.filtered("lambda").level is Level.OPERATIONAL


def test_capped_keeps_worst_and_counts_rest():
    comps = [Component(name=f"c{i}", level=Level.DEGRADED) for i in range(30)]
    comps.append(Component(name="bad", level=Level.MAJOR_OUTAGE))
    s = make(components=comps).capped(25)
    assert len(s.components) == 25
    assert s.components[0].name == "bad"
    assert s.more_components == 6
    assert s.level is Level.MAJOR_OUTAGE
    assert s.summary == "Major outage: bad, c0, c1, c2, c3 +26 more"


def test_capped_is_noop_when_small():
    s = make(components=[Component(name="a", level=Level.DEGRADED)])
    assert s.capped(25) is s


def test_latest_update_truncated():
    i = Incident(title="x", level=Level.DEGRADED, latest_update="a" * 2000)
    assert len(i.latest_update) == 500
    assert i.latest_update.endswith("…")


def test_dump_includes_computed_fields():
    data = make(error="boom").model_dump(mode="json")
    assert data["level"] == "unknown"
    assert data["summary"] == "Status unknown: boom"


def test_parse_dt_assumes_utc_for_naive_and_keeps_offsets():
    assert parse_dt(None) is None
    assert parse_dt("") is None
    assert parse_dt("2026-11-25T10:00:00") == datetime(2026, 11, 25, 10, tzinfo=UTC)
    assert parse_dt("2026-11-25T10:00:00Z") == datetime(2026, 11, 25, 10, tzinfo=UTC)
    assert parse_dt("2026-11-25T08:00:00-08:00").utcoffset() == timedelta(hours=-8)


def test_filtered_keeps_incidents_without_component_data():
    s = make(incidents=[Incident(title="Elevated errors", level=Level.PARTIAL_OUTAGE, components=[])])
    f = s.filtered("anything")
    assert len(f.incidents) == 1
    assert f.level is Level.PARTIAL_OUTAGE


def test_incident_title_truncated():
    i = Incident(title="t" * 500, level=Level.DEGRADED)
    assert len(i.title) == 200
    assert i.title.endswith("…")
