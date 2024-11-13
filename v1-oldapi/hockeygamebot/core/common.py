# -*- coding: utf-8 -*-

"""
This module contains all functions that might be used in multiple core modules.
"""
import logging

from hockeygamebot.models.gamestate import GameState
from hockeygamebot.social import socialhandler, twitter


def search_send_shotmap(game):
    search_account = "shotmaps"
    search_hashtag = game.game_hashtag
    search_term = f"from:{search_account} {search_hashtag}"

    tweets = twitter.search_twitter(search_term, 1)
    try:
        tweet = next(tweets)
        tweet_user = tweet.user.screen_name
        tweet_text = tweet.text
        tweet_id = tweet.id

        # If the period from the tweet doesn't match the game bot period, skip this loop
        game_final = True if game.game_state == GameState.FINAL.value else False
        current_period_check = "end of the game" if game_final else game.period.current_ordinal
        if current_period_check not in tweet_text:
            logging.info("Current Period: %s | Tweet Text: %s", current_period_check, tweet_text)
            raise ValueError("Period ordinal does not match tweet.")

        url = f"https://twitter.com/{tweet_user}/status/{tweet_id}"
        rt_text = f"⬇️ 5v5 & all situation shotmaps for {search_hashtag}.\n{url}"
        socialhandler.send(rt_text)
        return True

    except StopIteration:
        logging.warning("No tweets match the following - '%s'", search_term)
        return False
    except ValueError:
        logging.info("The tweet found does not match the current period - try again next loop.")
        return False
