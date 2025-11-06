from utils.team_details import get_team_details_by_name


class Team:
    """
    Represents an NHL team with attributes sourced from a predefined details dictionary.

    This class is designed to hold information about a specific NHL team, such as its
    name, hashtag, timezone, team ID, and primary/secondary colors. The team details
    are automatically populated based on the provided team name, using a helper function
    to look up the corresponding data.

    Attributes:
        full_name (str): The full name of the NHL team (e.g., "New Jersey Devils").
        hashtag (str): The team's associated social media hashtag (e.g., "#NJDevils").
        timezone (str): The timezone the team is based in (e.g., "America/New_York").
        team_id (int): The unique ID of the team.
        primary_color (str): The team's primary color in hexadecimal format (e.g., "#CE1126").
        secondary_color (str): The team's secondary color in hexadecimal format (e.g., "#000000").

    Methods:
        __str__(): Returns a human-readable string representation of the team.

    Raises:
        ValueError: If the team name is not found in the predefined team details dictionary.

    Example:
        home_team = Team("New Jersey Devils")
        print(home_team)  # Outputs: New Jersey Devils (#NJDevils)
    """

    def __init__(self, team_name):
        # Fetch the team details using the provided function
        team_data = get_team_details_by_name(team_name)

        if not team_data:
            raise ValueError(f"Team name '{team_name}' not found in TEAM_DETAILS - exiting!")

        # Populate attributes from the team details
        self.full_name = team_data["full_name"]
        self.abbreviation = team_data["abbreviation"]
        self.hashtag = team_data["hashtag"]
        self.timezone = team_data["timezone"]
        self.team_id = team_data["team_id"]
        self.primary_color = team_data["primary_color"]
        self.secondary_color = team_data["secondary_color"]
        self.primary_text_color = team_data["primary_text_color"]
        self.secondary_text_color = team_data["secondary_text_color"]

        self.score = 0
        self.goals = []

    def __str__(self):
        return f"{self.full_name} ({self.hashtag})"

    @staticmethod
    def is_tied(team1, team2):
        """
        Static method to check if the scores of two Team objects are tied.

        Args:
            team1 (Team): The first team object.
            team2 (Team): The second team object.

        Returns:
            bool: True if the scores are tied, False otherwise.
        """
        return team1.score == team2.score
