class Clock:
    """Represents the game clock for tracking time during an NHL game.

    The `Clock` class manages the current state of the game clock, including the
    time remaining in the period, the total seconds remaining, and whether the
    clock is running or in an intermission. The clock state is updated dynamically
    using data from the NHL play-by-play API.

    Attributes:
        time_remaining (str): The remaining time in the current period in "MM:SS" format.
            Defaults to "20:00".
        seconds_remaining (int): The remaining time in the current period in seconds.
            Defaults to 1200 (20 minutes).
        running (bool): Indicates whether the game clock is actively running.
            Defaults to `False`.
        in_intermission (bool): Indicates whether the game is currently in an intermission.
            Defaults to `False`.

    Methods:
        update(clock_data):
            Updates the game clock state using a dictionary from the play-by-play API.

    Example Usage:
        clock = Clock()
        clock_data = {
            "timeRemaining": "15:30",
            "secondsRemaining": 930,
            "running": True,
            "inIntermission": False
        }
        clock.update(clock_data)

        print(clock.time_remaining)  # Outputs: "15:30"
        print(clock.running)         # Outputs: True

    """

    def __init__(self):
        self.time_remaining = "20:00"
        self.seconds_remaining = 1200
        self.running = False
        self.in_intermission = False

    def update(self, clock_data):
        self.time_remaining = clock_data.get("timeRemaining", "20:00")
        self.seconds_remaining = clock_data.get("secondsRemaining", 1200)
        self.running = clock_data.get("running", False)
        self.in_intermission = clock_data.get("inIntermission", False)
