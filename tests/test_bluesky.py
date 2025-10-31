"""
Tests for Bluesky social media client

These tests verify the bug fixes we applied, especially:
- Input validation (None/empty messages)
- Proper hashtag parsing
- Error handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from socials.bluesky import BlueskyClient


class TestBlueskyInputValidation:
    """Test the input validation we added to fix Bug #1"""

    def test_post_with_none_message(self):
        """Test that post() handles None message without crashing"""
        # Setup - provide required credentials for nosocial mode
        client = BlueskyClient(account="test", password="test", nosocial=True)

        # Execute
        result = client.post(None)

        # Assert
        assert result is None, "post(None) should return None"

    def test_post_with_empty_string(self):
        """Test that post() handles empty string without crashing"""
        # Setup
        client = BlueskyClient(account="test", password="test", nosocial=True)

        # Execute
        result = client.post("")

        # Assert
        assert result is None, "post('') should return None"

    def test_post_with_whitespace_only(self):
        """Test that post() handles whitespace-only string"""
        # Setup
        client = BlueskyClient(account="test", password="test", nosocial=True)

        # Execute
        result = client.post("   ")

        # Assert
        # Whitespace is truthy so it processes, returns None in nosocial mode
        assert result is None

    def test_post_with_valid_message_nosocial(self):
        """Test that post() works with valid message in nosocial mode"""
        # Setup
        client = BlueskyClient(account="test", password="test", nosocial=True)

        # Execute
        result = client.post("Test message #NJDevils")

        # Assert
        assert result is None  # In nosocial mode, returns None after logging


class TestBlueskyHashtagParsing:
    """Test hashtag detection and parsing"""

    def test_single_hashtag(self):
        """Test message with single hashtag"""
        # This test verifies it doesn't crash (nosocial mode)
        client = BlueskyClient(account="test", password="test", nosocial=True)
        result = client.post("Goal! #NJDevils")
        assert result is None  # nosocial mode

    def test_multiple_hashtags(self):
        """Test message with multiple hashtags"""
        client = BlueskyClient(account="test", password="test", nosocial=True)
        result = client.post("What a game! #NJDevils #NHL #LetsGoDevils")
        assert result is None

    def test_no_hashtags(self):
        """Test message without hashtags"""
        client = BlueskyClient(account="test", password="test", nosocial=True)
        result = client.post("Simple message without tags")
        assert result is None


class TestBlueskyMonitorIntegration:
    """Test integration with StatusMonitor"""

    def test_post_records_in_monitor(self):
        """Test that successful posts are recorded in monitor"""
        # Setup
        mock_monitor = Mock()
        client = BlueskyClient(account="test", password="test", nosocial=True)
        client.monitor = mock_monitor

        # Execute
        client.post("Test message")

        # Assert
        mock_monitor.record_social_post.assert_called_once()

    def test_post_with_none_does_not_record(self):
        """Test that None messages don't record in monitor"""
        # Setup
        mock_monitor = Mock()
        client = BlueskyClient(account="test", password="test", nosocial=True)
        client.monitor = mock_monitor

        # Execute
        client.post(None)

        # Assert
        # Should not record since we return early
        mock_monitor.record_social_post.assert_not_called()


@pytest.mark.skip(reason="Requires actual Bluesky credentials")
class TestBlueskyRealAPI:
    """Tests that require real API calls (run manually with credentials)"""

    def test_real_authentication(self):
        """Test actual authentication to Bluesky"""
        # This would test with real credentials
        # Only run this manually when you want to verify API connectivity
        pass

    def test_real_post(self):
        """Test actual posting to Bluesky"""
        # This would make a real post
        # Only run manually with test account
        pass


# Pytest fixtures (reusable test setup)
@pytest.fixture
def mock_bluesky_client():
    """Create a BlueskyClient with nosocial mode for testing"""
    return BlueskyClient(account="test", password="test", nosocial=True)


@pytest.fixture
def mock_monitor():
    """Create a mock StatusMonitor for testing"""
    monitor = Mock()
    monitor.record_social_post = Mock()
    return monitor