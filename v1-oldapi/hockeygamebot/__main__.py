#  _                _                                         _           _
# | |              | |                                       | |         | |
# | |__   ___   ___| | _____ _   _  __ _  __ _ _ __ ___   ___| |__   ___ | |_
# | '_ \ / _ \ / __| |/ / _ \ | | |/ _` |/ _` | '_ ` _ \ / _ \ '_ \ / _ \| __|
# | | | | (_) | (__|   <  __/ |_| | (_| | (_| | | | | | |  __/ |_) | (_) | |_
# |_| |_|\___/ \___|_|\_\___|\__, |\__, |\__,_|_| |_| |_|\___|_.__/ \___/ \__|
#                             __/ | __/ |
#                            |___/ |___/


"""
Hockey Game Bot
~~~~~~~~~~~~~~~~~~~~~

An NHL game bot that sends important events & their details
to social media platforms (Twitter, Slack, Discord, etc).

"""

import logging

from hockeygamebot import app

if __name__ == "__main__":
    game = app.run()

    # All necessary Objects are created, start the game loop!
    logging.info("Starting main game loop now!")
    app.start_game_loop(game)
