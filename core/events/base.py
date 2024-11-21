import logging


class Event:
    def __init__(self, event_data, context):
        self.event_data = event_data
        self.event_type = event_data.get("typeDescKey", "unknown")
        self.period_number = event_data.get("periodDescriptor", {}).get("number", 0)
        self.time_in_period = event_data.get("timeInPeriod", "00:00")
        self.time_remaining = event_data.get("timeRemaining", "00:00")
        self.sort_order = event_data.get("sortOrder", 0)
        self.details = event_data.get("details", {})
        self.context = context

    def parse(self):
        pass

    def post_message(self):
        """
        Post the parsed message to the appropriate channel, if applicable.
        """
        message = self.parse()
        if message:
            self.context.bluesky_client.post(message)
