from hockeygamebot.helpers import utils


class Period(object):
    """Holds attributes related to the current period & time remaining."""

    def __init__(self):
        self.current = 1
        self.current_ordinal = "1st"
        self.time_remaining = "20:00"
        self.time_remaining_ss = 1200
        self.intermission = False
        self.intermission_remaining = 0
        self.current_oneminute_sent = False
        self.shotmap_retweet = False
