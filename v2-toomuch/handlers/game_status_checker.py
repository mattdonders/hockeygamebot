import logging
from datetime import timedelta


class GameStatusChecker:
    def __init__(self, nhl_service):
        self.nhl_service = nhl_service

    def check_game_status(self, team_abbrev, date):
        game_today, game_info = self.nhl_service.is_game_today(team_abbrev, date)
        if game_today:
            logging.info("Game scheduled for today.")
            return "today", game_info
        else:
            game_yesterday, prev_game = self.nhl_service.was_game_yesterday(team_abbrev, date)
            if game_yesterday:
                logging.info("There was a game yesterday.")
                return "yesterday", prev_game
            else:
                logging.info("No game scheduled for today or yesterday.")
                return "no_game", None
