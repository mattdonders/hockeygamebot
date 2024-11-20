import utils.others as otherutils


def get_player_name(player_id, roster):
    """
    Retrieve a player's name using their ID from the roster.
    """
    return roster.get(player_id, "Unknown Player")


def replace_ids_with_names(details, roster):
    """
    Replace fields ending with 'Id' in the details dictionary with their corresponding 'Name' fields,
    excluding fields ending in 'TeamId'.
    """
    for key, value in list(details.items()):  # Use list() to avoid runtime modification issues
        if key.endswith("Id") and not key.endswith("TeamId") and isinstance(value, int):
            player_name = roster.get(value, "Unknown Player")
            details[key.replace("Id", "Name")] = player_name
    return details


def parse_play_by_play_with_names(data, context):
    """
    Parse play-by-play data, dynamically replace player IDs with names,
    and send goal events to Bluesky.
    """
    if data.get("gameState") == "FUT":
        print("Game has not started yet. No events to parse.")
        return

    print(f"Bluesky client: {context.bluesky_client}")

    events = data.get("plays", [])
    parsed_events = []

    for event in events:
        event_type = event.get("typeDescKey", "unknown")
        details = event.get("details", {})

        # Replace player IDs with names dynamically
        details = replace_ids_with_names(details, context.combined_roster)

        # Add preferred team flag and adjust scores for goal events
        if event_type == "goal":
            event_owner_team_id = details.get("eventOwnerTeamId")
            is_preferred = event_owner_team_id == context.preferred_team_id
            details["is_preferred"] = is_preferred

            # Adjust scores based on the preferred team's home/away role
            if context.preferred_homeaway == "home":
                details["preferredScore"] = details["homeScore"]
                details["otherScore"] = details["awayScore"]
            else:
                details["preferredScore"] = details["awayScore"]
                details["otherScore"] = details["homeScore"]

            details.pop("homeScore", None)
            details.pop("awayScore", None)

            # Flatten and extract additional fields
            period_info = event.get("periodDescriptor", {})
            parsed_event = {
                "event_type": event_type,
                "period_number": period_info.get("number"),
                "period_type": period_info.get("periodType"),
                "max_regulation_periods": period_info.get("maxRegulationPeriods"),
                "time_in_period": event.get("timeInPeriod"),
                "time_remaining": event.get("timeRemaining"),
                "situation_code": event.get("situationCode"),
                "home_team_defending_side": event.get("homeTeamDefendingSide"),
                "sort_order": event.get("sortOrder"),
                "details": details,
            }

            parsed_events.append(parsed_event)

    for event in parsed_events:
        # print(event)
        if event["event_type"] == "goal":
            # print(event)
            message = format_goal_event(event, context.preferred_team_name, context.other_team_name)
            if message:
                print(message)
                context.bluesky_client.post(message)


def format_goal_event(event, preferred_team_name, other_team_name):
    """
    Format a goal event into a string for posting to Bluesky.
    """
    details = event["details"]
    period_number = event["period_number"]
    time_remaining = event["time_remaining"]
    scoring_player_name = details.get("scoringPlayerName", "Unknown Player")
    scoring_player_numgoals = details.get("scoringPlayerTotal", 1)
    assist_primary_player_name = details.get("assist1PlayerName", "None")
    assist_primary_player_numassists = details.get("assist1PlayerTotal", "None")
    assist_secondary_player_name = details.get("assist2PlayerName", "None")
    assist_secondary_player_numassists = details.get("assist2PlayerTotal", "None")
    shot_type = details.get("shotType", "unknown shot")
    preferred_score = details.get("preferredScore", 0)
    other_score = details.get("otherScore", 0)
    is_preferred = details.get("is_preferred", False)
    period_number = event.get("period_number", 1)
    period_number_ordinal = otherutils.ordinal(period_number)

    if is_preferred:
        goal_emoji = "🚨" * preferred_score
        return (
            f"{preferred_team_name} GOAL! {goal_emoji}\n\n"
            f"{scoring_player_name} ({scoring_player_numgoals}) scores on a {shot_type} shot with {time_remaining} remaining in the {period_number_ordinal} period.\n\n"
            f"🍎 {assist_primary_player_name} ({assist_primary_player_numassists})\n🍏 {assist_secondary_player_name} ({assist_secondary_player_numassists})\n\n"
            f"{preferred_team_name}: {preferred_score}\n"
            f"{other_team_name}: {other_score}"
        )
    else:
        goal_emoji = "👎" * other_score
        return (
            f"{other_team_name} scores. {goal_emoji}\n\n"
            f"{scoring_player_name} ({scoring_player_numgoals}) scores on a {shot_type} shot with {time_remaining} remaining in the {period_number_ordinal} period.\n\n"
            f"🍎 {assist_primary_player_name} ({assist_primary_player_numassists})\n🍏 {assist_secondary_player_name} ({assist_secondary_player_numassists})\n\n"
            f"{preferred_team_name}: {preferred_score}\n"
            f"{other_team_name}: {other_score}"
        )
