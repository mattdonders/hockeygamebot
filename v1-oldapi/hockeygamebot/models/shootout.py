class Shootout(object):
    """Attributes to track a shootout."""

    def __init__(self):
        self.preferred_score = []
        self.other_score = []
        self.shots = 0
        self.round = 1
        self.last_tweet = None
