""" Tests for 'stats.py' module. """

import pytest

from hockeygamebot.nhlapi import stats


def test_career_stats():
    career_stats = stats.get_player_career_stats(8475791)
    assert "assists" in career_stats
    assert "goals" in career_stats

    career_points_sum = career_stats["goals"] + career_stats["assists"]
    assert career_points_sum == career_stats["points"]

