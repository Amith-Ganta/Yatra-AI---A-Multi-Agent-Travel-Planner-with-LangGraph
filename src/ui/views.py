"""Draw a trip plan. The plan is the document ``src.agents.plan.build_plan`` returns."""

from typing import Any, Optional

import streamlit as st

from src.ui.formatting import (
    as_dict,
    budget_rows,
    dict_rows,
    escape_markdown,
    flight_rows,
    format_date,
    format_money,
    safe_link,
    text_list,
    weather_rows,
)

REJECTED_FALLBACK = "This request could not be turned into a trip plan."


def render_plan(plan: dict[str, Any]) -> None:
    """The whole plan: a status banner, the trip facts and one tab per agent."""
    if plan.get("status") == "rejected":
        st.warning(
            escape_markdown(plan.get("reason") or REJECTED_FALLBACK), icon=":material/block:"
        )
        return

    _banner(plan)
    _trip_facts(as_dict(plan.get("trip")))
    flights, hotels, weather, budget, itinerary = st.tabs(
        ["Flights", "Hotels", "Weather", "Budget", "Itinerary"]
    )
    with flights:
        _flights(as_dict(plan.get("flights")))
    with hotels:
        _hotels(as_dict(plan.get("hotels")))
    with weather:
        _weather(as_dict(plan.get("weather")))
    with budget:
        _budget(as_dict(plan.get("budget")))
    with itinerary:
        _itinerary(as_dict(plan.get("itinerary")))


def _banner(plan: dict[str, Any]) -> None:
    approval = as_dict(plan.get("approval"))
    status = plan.get("status")
    summary = escape_markdown(plan.get("summary") or "")
    if status == "approved":
        st.success(summary or "You approved this plan.", icon=":material/check_circle:")
    elif status == "revision_limit":
        st.warning(
            "You asked for changes until the revision limit "
            f"({approval.get('max_revisions')}) was reached. This is the latest draft and it was "
            "not approved.",
            icon=":material/error:",
        )
    else:
        st.info(summary or "Draft plan ready for your review.", icon=":material/rate_review:")

    revision = approval.get("revision") or 0
    if revision:
        # ``feedback_applied`` is a flag; the note says what changed, or why nothing did.
        applied = "Your feedback was applied" if approval.get("feedback_applied") is True else ""
        note = escape_markdown(approval.get("revision_note") or "")
        label = f"Revision {revision} of {approval.get('max_revisions')}"
        st.caption(" | ".join(part for part in (label, applied, note) if part))


def _trip_facts(trip: dict[str, Any]) -> None:
    destination = trip.get("destination") or "Not set"
    days = trip.get("days")
    columns = st.columns(4)
    columns[0].metric("Destination", str(destination))
    columns[1].metric("Dates", _date_range(trip), f"{days} days" if days else None, "off")
    columns[2].metric("Travellers", str(trip.get("party_size") or "-"))
    columns[3].metric("Budget", format_money(trip.get("budget")))


def _date_range(trip: dict[str, Any]) -> str:
    start, end = trip.get("start_date"), trip.get("end_date")
    if not start or not end:
        return "-"
    return f"{format_date(start)} to {format_date(end)}"


def _table(rows: list[dict[str, Any]], column_config: Optional[dict[str, Any]] = None) -> None:
    st.dataframe(  # pyright: ignore[reportUnknownMemberType]
        rows, hide_index=True, width="stretch", column_config=column_config
    )


def _empty(section: dict[str, Any], message: str) -> bool:
    """Say so when an agent produced nothing; True when the tab has nothing more to show."""
    if section:
        return False
    st.caption(message)
    return True


def _flights(section: dict[str, Any]) -> None:
    if _empty(section, "No flight search was run for this plan."):
        return
    best = as_dict(section.get("best_option"))
    if best:
        st.markdown(
            f"**Best option:** {escape_markdown(best.get('airline', 'Unknown airline'))}, "
            f"{escape_markdown(format_money(best.get('price')))} per person, "
            f"{escape_markdown(best.get('duration', '-'))}"
        )
    rows = flight_rows(section.get("flights"))
    if rows:
        _table(rows)
    if section.get("advice"):
        st.caption(escape_markdown(section["advice"]))


def _hotels(section: dict[str, Any]) -> None:
    if _empty(section, "No hotel search was run for this plan."):
        return
    if section.get("recommendations"):
        st.markdown(escape_markdown(section["recommendations"]))
    for hotel in dict_rows(section.get("hotels")):
        link = safe_link(hotel.get("url"))
        name = escape_markdown(hotel.get("name") or "Unnamed hotel")
        st.markdown(f"**[{name}]({link})**" if link else f"**{name}**")
        if hotel.get("description"):
            st.caption(escape_markdown(hotel["description"]))
    areas = text_list(section.get("neighborhoods"))
    if areas:
        st.markdown("**Areas to consider:** " + ", ".join(escape_markdown(area) for area in areas))


def _weather(section: dict[str, Any]) -> None:
    if _empty(section, "No forecast was fetched for this plan."):
        return
    rows = weather_rows(section.get("forecast"))
    if rows:
        _table(rows)
    if section.get("packing_advice"):
        st.markdown(f"**Packing:** {escape_markdown(section['packing_advice'])}")
    source = section.get("source")
    if source:
        st.caption(f"Forecast source: {escape_markdown(source)}")


def _budget(section: dict[str, Any]) -> None:
    if _empty(section, "No budget was worked out for this plan."):
        return
    left, right = st.columns(2)
    left.metric("Estimated total", format_money(section.get("total")))
    feasible = section.get("feasibility")
    right.metric("Within budget", "Yes" if feasible else "No")
    rows = budget_rows(section.get("categories"))
    if rows:
        # streamlit's own type hints leave these two calls partly unknown to pyright
        st.bar_chart(  # pyright: ignore[reportUnknownMemberType]
            rows, x="Category", y="Amount", horizontal=True
        )
        _table(rows, {"Amount": st.column_config.NumberColumn(format="$%d")})
    if section.get("advice"):
        (st.success if feasible else st.warning)(escape_markdown(section["advice"]))


def _itinerary(section: dict[str, Any]) -> None:
    if _empty(section, "No itinerary was drafted for this plan."):
        return
    for day in dict_rows(section.get("itinerary")):
        title = f"Day {day.get('day', '?')}, {format_date(day.get('date', ''))}"
        with st.expander(title, expanded=True):
            if day.get("weather"):
                st.caption(f"Forecast: {escape_markdown(day['weather'])}")
            for activity in text_list(day.get("activities")):
                st.markdown(f"- {escape_markdown(activity)}")
    highlights = text_list(section.get("highlights"))
    if highlights:
        st.markdown("**Highlights:** " + ", ".join(escape_markdown(item) for item in highlights))
    if section.get("notes"):
        st.caption(escape_markdown(section["notes"]))
