import logging


class StartOfGameSocial:
    """Tracks social media messages and statuses for the start of the game."""

    def __init__(self):
        self.counter = 0

        # Bluesky Root is the "Root Post" Of a Thread
        # Bluesky Parent is the "Last Post" In a Thread - the only we are replying to
        self.bluesky_root = None
        self.bluesky_parent = None

        self.core_msg = None
        self.core_sent = False
        self.season_series_msg = None
        self.season_series_sent = False
        self.team_stats_sent = False
        self.goalies_pref_msg = None
        self.goalies_pref_sent = False
        self.goalies_other_msg = None
        self.goalies_other_sent = False
        self.officials_msg = None
        self.officials_sent = False
        self.pref_lines_msg = None
        self.pref_lines_sent = False
        self.pref_lines_resent = False
        self.other_lines_msg = None
        self.other_lines_sent = False
        self.other_lines_resent = False

        # This is for starting lineups
        self.starters_sent = False
        self.starters_msg = None

    @property
    def all_pregame_sent(self):
        pregame_checks = ("core_sent", "season_series_sent", "officials_sent")
        status = {attr: getattr(self, attr) for attr in pregame_checks}
        if not all(status.values()):
            # Log the missing attributes and their values
            logging.info(f"Pregame Socials Status: %s", status)
        return all(status.values())


class EndOfGameSocial:
    """Tracks social media messages and statuses for the end of the game."""

    def __init__(self):
        self.retry_count = 0

        # Bluesky Root is the "Root Post" Of a Thread
        # Bluesky Parent is the "Last Post" In a Thread - the only we are replying to
        self.bluesky_root = None
        self.bluesky_parent = None

        # These attributes hold scraped values to avoid having to scrape multiple times
        self.hsc_homegs = None
        self.hsc_awaygs = None

        # These attributes hold messages and message sent boolean values
        self.final_score_msg = None
        self.final_score_sent = False
        self.three_stars_msg = None
        self.three_stars_sent = False
        self.nst_linetool_msg = None
        self.nst_linetool_sent = False
        self.hsc_msg = None
        self.hsc_sent = False
        self.shotmap_retweet = False
        self.team_stats_sent = False

    @property
    def all_social_sent(self):
        """Returns True / False depending on if all final socials were sent."""
        all_final_social = [v for k, v in self.__dict__.items() if "sent" in k]
        return all(all_final_social)

    @property
    def retries_exceeded(self):
        """Returns True if the number of retries (3 = default) has been exceeded."""
        return self.retry_count >= 3
