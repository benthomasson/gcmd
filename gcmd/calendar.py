"""Google Calendar operations — list meetings and find transcript docs."""

from datetime import datetime, timedelta, timezone

from .client import get_calendar_service, get_drive_service


def list_meetings(
    days: int = 7,
    max_results: int = 100,
    calendar_id: str = "primary",
) -> list[dict]:
    """List meetings with Google Meet from the last N days.

    Returns list of dicts with: id, summary, start, end, meet_link,
    organizer, attendees, attachments.
    """
    service = get_calendar_service()

    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=days)).isoformat()
    time_max = now.isoformat()

    results = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
        fields="items(id,summary,start,end,conferenceData,organizer,attendees,attachments,htmlLink)",
    ).execute()

    meetings = []
    for event in results.get("items", []):
        conf = event.get("conferenceData")
        if not conf:
            continue

        meet_link = None
        for ep in conf.get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                meet_link = ep.get("uri")
                break

        start = event.get("start", {})
        end = event.get("end", {})

        meetings.append({
            "id": event.get("id"),
            "summary": event.get("summary", "(No title)"),
            "start": start.get("dateTime", start.get("date", "")),
            "end": end.get("dateTime", end.get("date", "")),
            "meet_link": meet_link,
            "organizer": event.get("organizer", {}),
            "attendees": event.get("attendees", []),
            "attachments": event.get("attachments", []),
            "html_link": event.get("htmlLink"),
        })

    return meetings


def find_transcript_doc(meeting: dict) -> dict | None:
    """Find the transcript Google Doc for a meeting.

    Checks event attachments first, then searches Drive by meeting title.
    Returns dict with file id, name, and how it was found, or None.
    """
    for att in meeting.get("attachments", []):
        title = att.get("title", "").lower()
        if "transcript" in title:
            return {
                "file_id": att.get("fileId"),
                "name": att.get("title"),
                "method": "attachment",
            }

    summary = meeting.get("summary", "")
    if not summary:
        return None

    service = get_drive_service()
    query = (
        f"name contains '{summary}' and name contains 'Transcript' "
        f"and mimeType = 'application/vnd.google-apps.document' "
        f"and trashed = false"
    )

    try:
        results = service.files().list(
            q=query,
            pageSize=5,
            fields="files(id,name,modifiedTime)",
            orderBy="modifiedTime desc",
        ).execute()
    except Exception:
        return None

    files = results.get("files", [])
    if not files:
        return None

    return {
        "file_id": files[0]["id"],
        "name": files[0]["name"],
        "method": "search",
    }


def list_meetings_with_transcripts(
    days: int = 7,
    max_results: int = 100,
    calendar_id: str = "primary",
) -> list[dict]:
    """List recent meetings and resolve their transcript docs.

    Each returned dict has the meeting fields plus a 'transcript' key
    (dict with file_id/name/method, or None).
    """
    meetings = list_meetings(days=days, max_results=max_results, calendar_id=calendar_id)
    for m in meetings:
        m["transcript"] = find_transcript_doc(m)
    return meetings


def format_meetings(meetings: list[dict], verbose: bool = False) -> str:
    if not meetings:
        return "No meetings with Google Meet found."

    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"MEETINGS ({len(meetings)} total)")
    lines.append(f"{'='*70}\n")

    for m in meetings:
        start = m["start"]
        try:
            dt = datetime.fromisoformat(start)
            start_str = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            start_str = start

        transcript = m.get("transcript")
        if transcript:
            tx_marker = f"  [transcript: {transcript['file_id']}]"
        else:
            tx_marker = "  [no transcript]"

        lines.append(f"{start_str}  {m['summary']}{tx_marker}")

        if verbose:
            organizer = m.get("organizer", {})
            org_name = organizer.get("displayName") or organizer.get("email", "")
            lines.append(f"  Organizer: {org_name}")

            attendees = m.get("attendees", [])
            if attendees:
                names = [a.get("displayName") or a.get("email", "") for a in attendees[:5]]
                extra = f" +{len(attendees)-5} more" if len(attendees) > 5 else ""
                lines.append(f"  Attendees: {', '.join(names)}{extra}")

            if m.get("meet_link"):
                lines.append(f"  Meet: {m['meet_link']}")

            if transcript:
                lines.append(f"  Transcript: {transcript['name']} (found via {transcript['method']})")

            lines.append("")

    lines.append(f"{'='*70}\n")
    return "\n".join(lines)
